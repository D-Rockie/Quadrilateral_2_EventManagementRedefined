import sqlite3
import streamlit as st
import pandas as pd
import os
import requests
import cohere
import logging
from textblob import TextBlob
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from datetime import datetime, timedelta
from streamlit_option_menu import option_menu
from streamlit_folium import folium_static
import folium
import math  # Added for exponential decay in calculate_trend_scores

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API setup
COHERE_API_KEY = "RF13gvo9zsvPvfJYXz8cXEIylIiGWwkeyJQkxL34"
co = cohere.Client(COHERE_API_KEY)

# Constants
CATEGORIES = ["Technology", "Music", "Sports", "Art", "Business", "Games", "Movies", "Food", "Products"]
MOOD_MAPPING = {"positive": ["Sports", "Music", "Games"], "negative": ["Art"], "neutral": CATEGORIES}
FEEDBACK_FILE = "feedback.csv"
USER_LOCATIONS_FILE = "user_locations.csv"
STALLS_FILE = "stalls.csv"
BACKEND_URL = "http://127.0.0.1:5000"
STALLS = ["Food Stall", "Tech Stall", "Merchandise Stall", "Game Stall"]

# --- Database Setup ---
def get_db_connection():
    conn = sqlite3.connect('emr.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        interests TEXT
    )''')
    cursor.execute('''SELECT count(*) FROM sqlite_master WHERE type='table' AND name='events' ''')
    if cursor.fetchone()[0] == 1:
        cursor.execute('''PRAGMA table_info(events)''')
        columns = {row[1] for row in cursor.fetchall()}
        if 'created_by' not in columns:
            cursor.execute('''ALTER TABLE events ADD COLUMN created_by INTEGER''')
            logger.info("Added 'created_by' column to events table.")
    else:
        cursor.execute('''CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            date TEXT,
            venue TEXT,
            description TEXT,
            category TEXT NOT NULL,
            created_by INTEGER,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )''')
    cursor.execute('''SELECT count(*) FROM sqlite_master WHERE type='table' AND name='registrations' ''')
    if cursor.fetchone()[0] == 1:
        # Check if registration_date exists, if not, add it without default, then update existing rows
        cursor.execute('''PRAGMA table_info(registrations)''')
        columns = {row[1] for row in cursor.fetchall()}
        if 'registration_date' not in columns:
            cursor.execute('''ALTER TABLE registrations ADD COLUMN registration_date TEXT''')
            # Update existing rows with a default timestamp (e.g., current time)
            cursor.execute('''UPDATE registrations SET registration_date = ? WHERE registration_date IS NULL''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
            logger.info("Added 'registration_date' column to registrations table and updated existing rows.")
    else:
        cursor.execute('''CREATE TABLE registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            event_id INTEGER,
            registration_date TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (event_id) REFERENCES events(id)
        )''')
    conn.commit()
    conn.close()

# --- CSV Initialization ---
def initialize_csv():
    if not os.path.exists(FEEDBACK_FILE):
        pd.DataFrame(columns=["name", "feedback", "stall", "rating", "response"]).to_csv(FEEDBACK_FILE, index=False)
        logger.info("Initialized feedback CSV file.")
    if not os.path.exists(USER_LOCATIONS_FILE):
        pd.DataFrame(columns=["user_id", "latitude", "longitude", "timestamp"]).to_csv(USER_LOCATIONS_FILE, index=False)
        logger.info("Initialized user locations CSV file.")
    if not os.path.exists(STALLS_FILE):
        pd.DataFrame(columns=["user_id", "stall_name", "latitude", "longitude"]).to_csv(STALLS_FILE, index=False)
        logger.info("Initialized stalls CSV file.")
    if not os.path.exists("user_interests.csv"):
        pd.DataFrame(columns=["id", "name", "email", "interests"]).to_csv("user_interests.csv", index=False)
        logger.info("Initialized user interests CSV file.")
    if not os.path.exists("user_id_interests.csv"):
        pd.DataFrame(columns=["id", "interests"]).to_csv("user_id_interests.csv", index=False)
        logger.info("Initialized user ID and interests CSV file.")

# --- Feedback Functions ---
def load_feedback():
    if os.path.exists(FEEDBACK_FILE):
        return pd.read_csv(FEEDBACK_FILE)
    return pd.DataFrame(columns=["name", "feedback", "stall", "rating", "response"])

def save_feedback(df):
    df.to_csv(FEEDBACK_FILE, index=False)

def submit_feedback():
    st.markdown("<h2 class='section-title'>Share Your Feedback</h2>", unsafe_allow_html=True)
    name = st.text_input("Your Name", placeholder="Enter your name")
    feedback = st.text_area("Feedback", placeholder="What did you think?")
    stall = st.selectbox("Stall", STALLS)
    rating = st.slider("Rating", 1, 5, 3, help="Rate from 1 (poor) to 5 (excellent)")
    if st.button("Submit Feedback"):
        df = load_feedback()
        df = pd.concat([df, pd.DataFrame([{"name": name, "feedback": feedback, "stall": str(stall), "rating": rating, "response": ""}])], ignore_index=True)
        save_feedback(df)
        st.success("Feedback submitted successfully!")
        logger.info(f"Feedback submitted for {stall} by {name}")

def analyze_event_performance():
    st.markdown("<h2 class='section-title'>Event Insights</h2>", unsafe_allow_html=True)
    df = load_feedback()
    if df.empty:
        st.write("No feedback available.")
        return
    stall_selected = st.selectbox("Select Stall to Analyze", df["stall"].dropna().unique())
    stall_feedback = df[df["stall"] == stall_selected]
    feedback_text = " ".join(stall_feedback["feedback"].dropna().tolist())
    try:
        response = co.generate(model="command", prompt=f"Analyze feedback for {stall_selected} and summarize event performance: {feedback_text}")
        prediction = response.generations[0].text
        logger.info(f"Generated performance prediction for {stall_selected}")
    except Exception as e:
        prediction = f"Error fetching prediction: {str(e)}"
        logger.error(f"Cohere error in performance prediction: {str(e)}")
    st.subheader(f"Predicted Performance for {stall_selected}")
    st.write(prediction)

def recommend_stalls():
    st.markdown("<h2 class='section-title'>Stall Recommendations</h2>", unsafe_allow_html=True)
    df = load_feedback()
    if df.empty:
        st.write("No feedback available to generate recommendations.")
        return
    user_interest = st.selectbox("Select a stall you are interested in", df["stall"].dropna().unique())
    feedback_text = " ".join(df[df["stall"] == user_interest]["feedback"].dropna().tolist())
    if not feedback_text:
        st.write(f"No feedback available for {user_interest} to generate recommendations.")
        return
    try:
        response = co.generate(
            model="command",
            prompt=f"Based on past feedback and event performance, suggest the best stalls for a user interested in {user_interest}. Feedback data: {feedback_text}"
        )
        recommendation = response.generations[0].text
        logger.info(f"Generated stall recommendation for interest: {user_interest}")
    except Exception as e:
        recommendation = f"Error fetching recommendation: {str(e)}"
        logger.error(f"Cohere error in stall recommendation: {str(e)}")
    st.subheader("Recommended Stalls")
    st.write(recommendation)

def admin_dashboard():
    st.markdown("<h2 class='section-title'>Admin Dashboard</h2>", unsafe_allow_html=True)
    password = st.text_input("Admin Password", type="password")
    if password != "admin123":
        st.warning("Incorrect password!")
        return
    df = load_feedback()
    if df.empty:
        st.write("No feedback to display.")
        return
    st.subheader("Feedback Overview")
    selected_stall = st.selectbox("Select Stall", df["stall"].dropna().unique())
    stall_feedback = df[df["stall"] == selected_stall]
    st.write(stall_feedback)
    reply_option = st.radio("Do you want to reply to feedback?", ["No", "Yes"])
    if reply_option == "Yes":
        feedback_options = stall_feedback[stall_feedback["response"].isna() | (stall_feedback["response"] == "")]
        if feedback_options.empty:
            st.write("No feedback available to reply.")
            return
        selected_feedback = st.selectbox("Select feedback to reply", feedback_options.index)
        row = df.loc[selected_feedback]
        st.subheader(f"Feedback from {row['name']} ({row['stall']})")
        st.write(row["feedback"])
        response = st.text_area("Your Response")
        if st.button("Submit Response"):
            df.at[selected_feedback, "response"] = response
            save_feedback(df)
            st.success("Response submitted!")
            st.rerun()
    st.subheader("Delete Feedback")
    delete_option = st.radio("Do you want to delete a feedback?", ["No", "Yes"])
    if delete_option == "Yes":
        delete_feedback = st.selectbox("Select feedback to delete", stall_feedback.index)
        if st.button("Delete Feedback"):
            df = df.drop(index=delete_feedback)
            save_feedback(df)
            st.success("Feedback deleted successfully!")
            st.rerun()
    st.subheader("Analytics")
    st.write(f"Total feedback received for {selected_stall}: {len(stall_feedback)}")
    rating_counts = stall_feedback["rating"].value_counts().sort_index()
    fig, ax = plt.subplots()
    ax.pie(rating_counts, labels=rating_counts.index, autopct='%1.1f%%', startangle=90, colors=["#ff9999","#66b3ff","#99ff99","#ffcc99","#c2c2f0"])
    ax.axis('equal')
    st.pyplot(fig)
    
    # Add button to extract user IDs and interests to CSV
    if st.button("Export User IDs and Interests to CSV"):
        extract_user_id_interests_to_csv()
        st.success("User IDs and interests exported to user_id_interests.csv!")

# --- Location and Crowd Functions ---
def share_location(user_id, latitude, longitude, is_stall_owner=False, stall_name=""):
    if not all([user_id, latitude, longitude]):
        st.error("User ID, Latitude, and Longitude are required!")
        return False
    try:
        data = {
            "user_id": user_id,
            "latitude": float(latitude),
            "longitude": float(longitude),
            "is_stall_owner": is_stall_owner,
            "stall_name": stall_name if is_stall_owner else ""
        }
        response = requests.post(f"{BACKEND_URL}/update_location", json=data, timeout=10)
        if response.status_code == 200:
            st.success("Location shared successfully!")
            return True
        else:
            st.error(f"Error: {response.json().get('error', 'Unknown error')}")
            return False
    except requests.RequestException as e:
        st.error(f"Network error: {str(e)}")
        return False

def check_crowd_density():
    try:
        response = requests.get(f"{BACKEND_URL}/crowd_density", timeout=10)
        if response.status_code == 200:
            crowd_data = response.json()
            if "error" in crowd_data:
                st.info(crowd_data["error"])
                return
            st.markdown("### Crowd Levels")
            stall_names = []
            crowd_counts = []
            for stall, details in crowd_data.items():
                stall_names.append(stall)
                crowd_counts.append(details["crowd_count"])
                crowd_level = details["crowd_level"].lower().replace(" ", "-")
                icon = "👥"
                st.markdown(f"""
                    <div class="crowd-level {crowd_level}">
                        <span class="crowd-icon">{icon}</span>
                        <span><strong>{stall}</strong>: {details['crowd_level']} ({details['crowd_count']} people)</span>
                    </div>
                """, unsafe_allow_html=True)
            fig = go.Figure(data=[
                go.Bar(
                    x=stall_names,
                    y=crowd_counts,
                    marker_color=['#006400' if count <= 1 else '#b3e6b3' if count <= 3 else '#fff9e6' if count <= 5 else '#ffe6e6' if count <= 7 else '#ffcccc' for count in crowd_counts],
                    width=0.2
                )
            ])
            fig.update_layout(
                title="Crowd Count by Stall",
                xaxis_title="Stalls",
                yaxis_title="Number of People",
                plot_bgcolor='white',
                paper_bgcolor='white',
                bargap=0.3,
                bargroupgap=0.1,
                font=dict(size=12, color='black'),
                height=400,
                width=600,
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error(f"Error fetching crowd density data. Status: {response.status_code}, Response: {response.text}")
    except requests.RequestException as e:
        st.error(f"Network error: {str(e)}")
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")

def suggest_best_stall(user_id):
    try:
        print(f"Requesting stall suggestion for user_id: {user_id}")  # Debug log
        response = requests.post(f"{BACKEND_URL}/suggest_stall", json={"user_id": user_id}, timeout=10)
        if response.status_code == 200:
            suggestion = response.json()
            print(f"Received suggestion: {suggestion}")  # Debug log
            if "error" in suggestion:
                st.warning(suggestion["error"])
            else:
                st.markdown(f"""
                    <div class="suggestion-message">
                        Recommended Stall: {suggestion['stall']}<br>
                        Reason: {suggestion['reason']}
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.error(f"Error fetching stall suggestion. Status: {response.status_code}, Response: {response.text}")
    except requests.RequestException as e:
        st.error(f"Network error: {str(e)}")
        print(f"Network error details: {str(e)}")  # Debug log
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")
        print(f"Unexpected error details: {str(e)}")  # Debug log

# --- Event Management Functions ---
def generate_event_description(title, category, date=None, venue=None):
    prompt = f"Generate a concise and exciting description for {title} in the {category} category. Highlight the appeal for attendees."
    if date and venue:
        prompt += f" Scheduled on {date} at {venue}."
    else:
        prompt += " in an unspecified location."
    try:
        response = co.generate(
            model="command",
            prompt=prompt,
            max_tokens=150,
            temperature=0.7,
            num_generations=1
        )
        return response.generations[0].text.strip()
    except Exception as e:
        logger.error(f"Cohere generation error: {e}")
        return ""

def add_user(name, email, interests):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (name, email, interests) VALUES (?, ?, ?)",
                   (name, email, ",".join(interests)))
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    
    # Save to CSV
    user_data = pd.DataFrame([{"id": user_id, "name": name, "email": email, "interests": ",".join(interests)}])
    if os.path.exists("user_interests.csv"):
        existing_data = pd.read_csv("user_interests.csv")
        updated_data = pd.concat([existing_data, user_data], ignore_index=True)
    else:
        updated_data = user_data
    updated_data.to_csv("user_interests.csv", index=False)
    logger.info(f"User interests for {name} (ID: {user_id}) saved to CSV and database.")
    
    return user_id

def get_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def add_event(title, date, venue, description, category, created_by):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO events (title, date, venue, description, category, created_by) VALUES (?, ?, ?, ?, ?, ?)",
                   (title, date, venue, description, category, created_by))
    conn.commit()
    event_id = cursor.lastrowid
    conn.close()
    logger.info(f"Event '{title}' (ID: {event_id}) added by user {created_by}")
    return event_id

def get_all_events():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events ORDER BY id DESC")
    events = cursor.fetchall()
    conn.close()
    logger.info(f"Retrieved {len(events)} events from database")
    return events

def delete_event(event_id, user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT created_by FROM events WHERE id = ?", (event_id,))
    event = cursor.fetchone()
    if not event or event['created_by'] != user_id:
        conn.close()
        return False
    cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
    cursor.execute("DELETE FROM registrations WHERE event_id = ?", (event_id,))
    conn.commit()
    conn.close()
    logger.info(f"Event {event_id} deleted by user {user_id}")
    return True

def get_interest_based_events(user_id):
    user = get_user(user_id)
    if not user or not user['interests']:
        return []
    interests = user['interests'].split(',')
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM events WHERE category IN ({})".format(','.join('?' * len(interests)))
    cursor.execute(query, interests)
    recommended = cursor.fetchall()
    conn.close()
    return recommended

def get_mood_based_events(mood_input):
    if not mood_input:
        return []
    blob = TextBlob(mood_input)
    sentiment = blob.sentiment.polarity
    mood = "positive" if sentiment > 0.3 else "negative" if sentiment < -0.3 else "neutral"
    mood_categories = MOOD_MAPPING[mood]
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM events WHERE category IN ({})".format(','.join('?' * len(mood_categories)))
    cursor.execute(query, mood_categories)
    mood_events = cursor.fetchall()
    conn.close()
    return mood_events

def register_for_event(user_id, event_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM registrations WHERE user_id = ? AND event_id = ?", (user_id, event_id))
    if cursor.fetchone():
        conn.close()
        return False
    cursor.execute("INSERT INTO registrations (user_id, event_id, registration_date) VALUES (?, ?, CURRENT_TIMESTAMP)", (user_id, event_id))
    conn.commit()
    conn.close()
    return True

def get_user_registrations(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT e.* FROM events e JOIN registrations r ON e.id = r.event_id WHERE r.user_id = ?", (user_id,))
    registrations = cursor.fetchall()
    conn.close()
    return registrations

# --- Trend-Based Recommendation Functions ---
def calculate_trend_scores(user_id, decay_rate=0.02):
    conn = get_db_connection()
    cursor = conn.cursor()
    # Use id as a fallback if registration_date is missing
    cursor.execute("""
        SELECT e.category, r.registration_date, r.id 
        FROM registrations r 
        JOIN events e ON r.event_id = e.id 
        WHERE r.user_id = ?
    """, (user_id,))
    bookings = cursor.fetchall()
    conn.close()
    
    if not bookings:
        return {}
    
    category_scores = {}
    current_date = datetime.now()
    
    # Get the range of registration IDs to estimate time, handling empty or invalid IDs
    booking_ids = [booking['id'] for booking in bookings if 'id' in booking and booking['id'] is not None]
    if not booking_ids:
        return {}  # No valid IDs, return empty scores
    
    min_id = min(booking_ids)
    max_id = max(booking_ids)
    id_range = max_id - min_id if max_id > min_id else 1  # Avoid division by zero
    
    for booking in bookings:
        try:
            # Safely access category, default to None if missing
            category = booking['category'] if 'category' in booking else None
            if not category:
                continue  # Skip if category is missing
            
            # Handle case where registration_date might be None or missing
            reg_date_str = booking["registration_date"]
            if reg_date_str:
                try:
                    reg_date = datetime.strptime(reg_date_str, "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    # Fallback: Estimate date based on registration ID
                    if 'id' in booking and booking['id'] is not None:
                        if id_range > 0:
                            # Assume IDs are sequential and spread over a reasonable time (e.g., 90 days)
                            days_ago = int((max_id - booking['id']) * 90 / id_range)  # Spread over 90 days
                            reg_date = current_date - timedelta(days=days_ago)
                        else:
                            reg_date = current_date - timedelta(days=30)  # Default to 30 days ago if no range
                    else:
                        reg_date = current_date - timedelta(days=30)  # Default if ID is missing
            else:
                # If registration_date is missing, estimate based on ID
                if 'id' in booking and booking['id'] is not None:
                    if id_range > 0:
                        days_ago = int((max_id - booking['id']) * 90 / id_range)  # Spread over 90 days
                        reg_date = current_date - timedelta(days=days_ago)
                    else:
                        reg_date = current_date - timedelta(days=30)  # Default to 30 days ago
                else:
                    reg_date = current_date - timedelta(days=30)  # Default if ID is missing
            
            # Calculate days ago, ensuring it's not negative
            days_ago = (current_date - reg_date).days
            if days_ago < 0:  # Ensure days_ago is not negative (future dates)
                days_ago = 0
            
            # Calculate weight using exponential decay, with safety checks
            if not isinstance(decay_rate, (int, float)) or decay_rate < 0:
                decay_rate = 0.02  # Default to 0.02 if invalid
            if not isinstance(days_ago, (int, float)) or days_ago < 0:
                days_ago = 0  # Default to 0 if invalid
            
            weight = math.exp(-decay_rate * days_ago)  # Exponential decay
            
            # Update category scores
            category_scores[category] = category_scores.get(category, 0) + weight
        except KeyError as e:
            logger.error(f"KeyError in booking data: {e} - Skipping entry for user {user_id}")
            continue
        except Exception as e:
            logger.error(f"Unexpected error processing booking for user {user_id}: {e}")
            continue
    
    return category_scores

def get_trend_based_events(user_id):
    scores = calculate_trend_scores(user_id)
    if not scores:
        return []
    top_category = max(scores, key=scores.get)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    current_date_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT * 
        FROM events 
        WHERE category = ? AND date > ? 
        ORDER BY date ASC 
        LIMIT 3
    """, (top_category, current_date_str))
    recommendations = cursor.fetchall()
    conn.close()
    return recommendations

# --- UI Display Function ---
def display_event(event, show_register=False, show_delete=False, user_id=None, creator_id=None, page=None):
    with st.container():
        st.markdown(f"""
            <div class="event-card">
                <h3 style="color: #ffffff;">{event['title']} 🎉</h3>
                <p style="color: #ffffff;">📅 <strong>Date:</strong> {event['date'] if event['date'] else 'Not specified'}</p>
                <p style="color: #ffffff;">📍 <strong>Venue:</strong> {event['venue'] if event['venue'] else 'Not specified'}</p>
                <p style="color: #ffffff;">🏷️ <strong>Category:</strong> {event['category']}</p>
                <p style="color: #ffffff;">{event['description']}</p>
            </div>
        """, unsafe_allow_html=True)
        col1, col2 = st.columns([3, 1])
        with col2:
            if show_register and user_id:
                # Use page name and event_id to ensure unique keys
                unique_key = f"reg_{page}_{event['id']}" if page else f"reg_{event['id']}"
                if st.button("Register", key=unique_key):
                    if register_for_event(user_id, event['id']):
                        st.success(f"Registered for {event['title']}!")
                    else:
                        st.warning("You’re already registered for this event.")
            if show_delete and user_id and user_id == creator_id:
                # Use page name and event_id for unique delete keys as well
                unique_key = f"del_{page}_{event['id']}" if page else f"del_{event['id']}"
                if st.button("Delete", key=unique_key):
                    if delete_event(event['id'], user_id):
                        st.success(f"Event '{event['title']}' deleted successfully!")
                        st.rerun()
                    else:
                        st.error("You are not authorized to delete this event.")

# --- Database Utility Functions ---
def extract_user_id_interests_to_csv():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, interests FROM users")
    users = cursor.fetchall()
    conn.close()
    
    # Create a list of dictionaries for the DataFrame
    user_data = [{"id": row["id"], "interests": row["interests"]} for row in users]
    
    # Create a DataFrame
    df = pd.DataFrame(user_data)
    
    # Save to CSV
    df.to_csv("user_id_interests.csv", index=False)
    logger.info("User IDs and interests extracted and saved to user_id_interests.csv")

# --- Streamlit App ---
def main():
    initialize_csv()
    init_db()

    # Custom CSS for UI (combining styles from all documents)
    st.markdown("""
        <style>
            .main { background-color: #f5f5f5; padding: 20px; border-radius: 10px; }
            .stButton>button { background-color: #4CAF50; color: white; border-radius: 5px; padding: 10px 20px; font-size: 14px; }
            .stButton>button:hover { background-color: #45a049; }
            .sidebar .sidebar-content { background-color: #2c3e50; color: white; }
            .sidebar h2 { color: #ecf0f1; }
            .event-card { 
                background-color: #000000; 
                padding: 20px; 
                margin-bottom: 20px; 
                border-radius: 15px; 
                box-shadow: 0 4px 10px rgba(0,0,0,0.1); 
                max-width: 100%; 
                overflow: auto; 
                word-wrap: break-word; 
            }
            .header { color: #2c3e50; font-family: 'Arial', sans-serif; }
            .banner { background: #00b4d8; padding: 20px; text-align: center; color: white; border-radius: 10px; margin-bottom: 20px; }
            .banner h1 { font-size: 32px; margin: 0; }
            .section-title { color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 5px; }
            .stTextInput>label, .stSelectbox>label { color: #2c3e50; font-weight: bold; }
            .crowd-level { padding: 10px; margin: 5px; border-radius: 5px; display: flex; align-items: center; justify-content: space-between; }
            .very-low { background-color: #e0f7e9; color: #006400; }
            .low { background-color: #b3e6b3; color: #006400; }
            .medium { background-color: #fff9e6; color: #8b4513; }
            .high { background-color: #ffe6e6; color: #ff4500; }
            .very-high { background-color: #ffcccc; color: #ff0000; }
            .crowd-icon { margin-right: 10px; font-size: 20px; }
            .update-button {
                background-color: #4CAF50; /* Green */
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 16px;
                margin-right: 10px;
                transition: background-color 0.3s;
            }
            .update-button:hover {
                background-color: #45a049; /* Darker green on hover */
            }
            .update-button:disabled {
                background-color: #cccccc;
                cursor: not-allowed;
            }
            .suggest-button {
                background-color: #2196F3; /* Blue */
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 16px;
                margin-right: 10px;
                transition: background-color 0.3s;
            }
            .suggest-button:hover {
                background-color: #1976D2; /* Darker blue on hover */
            }
            .suggestion-message {
                background-color: #e8f5e9; /* Light green background */
                color: #2e7d32; /* Dark green text */
                padding: 12px 15px;
                border-radius: 5px;
                margin-top: 10px;
                font-size: 16px;
                border-left: 4px solid #4CAF50; /* Green border for emphasis */
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); /* Subtle shadow for depth */
            }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="banner"><h1>EventHub</h1><p>Your All-in-One Event Experience</p></div>', unsafe_allow_html=True)

    # Initialize session state for navigation and other states
    if 'page' not in st.session_state:
        st.session_state.page = "Home"
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
    if 'stall_registered' not in st.session_state:
        st.session_state.stall_registered = False

    # Sidebar Navigation with Option Menu
    with st.sidebar:
        st.markdown("<h2>Explore EventHub</h2>", unsafe_allow_html=True)
        page = option_menu(
            menu_title=None,
            options=["Home", "Register", "All Events", "My Events", "Recommendations", "Add Event", "Feedback", "Performance Insights", "Stall Suggestions", "Crowd Monitor", "Admin Dashboard"],
            icons=["house", "person-plus", "calendar", "bookmark", "lightbulb", "plus-circle", "chat", "graph-up", "shop", "people", "shield-lock"],
            default_index=0,
            styles={
                "container": {"padding": "0!important", "background-color": "#2c3e50"},
                "icon": {"color": "#ecf0f1", "font-size": "18px"},
                "nav-link": {"color": "#ecf0f1", "font-size": "16px", "text-align": "left", "margin": "0px", "--hover-color": "#3498db"},
                "nav-link-selected": {"background-color": "#3498db"},
            }
        )
        # Sync session state with sidebar selection
        if page != st.session_state.page:
            st.session_state.page = page
            st.rerun()

    with st.container():
        if st.session_state.page == "Home":
            st.markdown("<h2 class='section-title'>Welcome to EventHub</h2>", unsafe_allow_html=True)
            st.write("Discover events, connect with others, and manage your experiences seamlessly.")
            st.markdown("<h3>Log In</h3>", unsafe_allow_html=True)
            user_id = st.number_input("Your User ID", min_value=1, step=1)
            if st.button("Log In"):
                user = get_user(user_id)
                if user:
                    st.session_state.user_id = user_id
                    st.success(f"Logged in as {user['name']}!")
                else:
                    st.error("Invalid User ID. Please register first.")
            if st.button("New User? Register Here", key="register_button"):
                st.session_state.page = "Register"  # Set page to "Register"
                st.rerun()  # Rerun to navigate to the Register page
            st.markdown("<h3>Featured Events</h3>", unsafe_allow_html=True)
            events = get_all_events()
            if events:
                st.write("Explore our top picks!")
                for event in events[:3]:
                    display_event(event, show_register=True, user_id=st.session_state.user_id, creator_id=event['created_by'], page="Home")
            else:
                st.write("No events available yet.")

        elif st.session_state.page == "Register":
            st.markdown("<h2 class='section-title'>Join EventHub</h2>", unsafe_allow_html=True)
            with st.form("register_form"):
                st.subheader("Create Your Profile")
                name = st.text_input("Name", placeholder="Enter your full name")
                email = st.text_input("Email", placeholder="Enter your email")
                interests = st.multiselect("Your Interests", CATEGORIES, help="Pick what excites you!")
                submit_register = st.form_submit_button("Sign Up")
                if submit_register:
                    if not name or not email or not interests:
                        st.error("All fields are required to register.")
                    else:
                        user_id = add_user(name, email, interests)
                        st.success(f"Registered successfully! Your User ID is {user_id}. Log in on the Home page.")
                        st.session_state.user_id = user_id
                        st.session_state.page = "Home"  # Return to Home after registration
                        st.rerun()

        elif st.session_state.page == "All Events":
            st.markdown("<h2 class='section-title'>Upcoming Events</h2>", unsafe_allow_html=True)
            st.write("Browse all events happening soon.")
            events = get_all_events()
            if events:
                for event in events:
                    display_event(event, show_register=True, show_delete=True, user_id=st.session_state.user_id, creator_id=event['created_by'], page="All_Events")
            else:
                st.write("No events available yet.")

        elif st.session_state.page == "My Events":
            st.markdown("<h2 class='section-title'>My Events</h2>", unsafe_allow_html=True)
            if not st.session_state.user_id:
                st.warning("Please log in first.")
            else:
                registrations = get_user_registrations(st.session_state.user_id)
                if registrations:
                    for event in registrations:
                        display_event(event, show_delete=True, user_id=st.session_state.user_id, creator_id=event['created_by'], page="My_Events")
                else:
                    st.write("You haven’t registered for any events yet.")

        elif st.session_state.page == "Recommendations":
            st.markdown("<h2 class='section-title'>Tailored for You</h2>", unsafe_allow_html=True)
            if not st.session_state.user_id:
                st.warning("Please log in first.")
            else:
                tab1, tab2, tab3 = st.tabs(["Interest-Based Picks", "Mood-Based Suggestions", "Trend-Based Picks"])
                with tab1:
                    st.subheader("Based on Your Interests")
                    interest_events = get_interest_based_events(st.session_state.user_id)
                    if interest_events:
                        for event in interest_events:
                            display_event(event, show_register=True, user_id=st.session_state.user_id, creator_id=event['created_by'], page="Recommendations_Interest")
                    else:
                        st.write("No interest-based recommendations yet.")
                with tab2:
                    st.subheader("Based on Your Mood")
                    mood_input = st.text_input("How are you feeling today?", placeholder="Happy, sad, excited...")
                    if mood_input:
                        mood_events = get_mood_based_events(mood_input)
                        if mood_events:
                            for event in mood_events:
                                display_event(event, show_register=True, user_id=st.session_state.user_id, creator_id=event['created_by'], page="Recommendations_Mood")
                        else:
                            st.write("No mood-based events available right now.")
                    else:
                        st.write("Enter your mood to see recommendations!")
                with tab3:
                    st.subheader("Based on Your Recent Trends")
                    trend_events = get_trend_based_events(st.session_state.user_id)
                    if trend_events:
                        for event in trend_events:
                            display_event(event, show_register=True, user_id=st.session_state.user_id, creator_id=event['created_by'], page="Recommendations_Trend")
                    else:
                        st.write("No trend-based recommendations yet. Register for more events to see suggestions!")

        elif st.session_state.page == "Add Event":
            st.markdown("<h2 class='section-title'>Create an Event</h2>", unsafe_allow_html=True)
            with st.form("event_form"):
                st.subheader("Event Details")
                title = st.text_input("Title", placeholder="e.g., Tech Conference 2025")
                date = st.date_input("Date")
                venue = st.text_input("Venue", placeholder="e.g., City Convention Center")
                description = st.text_area("Description", placeholder="Tell us about your event...")
                category = st.selectbox("Category", CATEGORIES)
                generate_desc = st.checkbox("Auto-Generate Description")
                if generate_desc and title and category:
                    generated_desc = generate_event_description(title, category, str(date), venue)
                    description = st.text_area("Generated Description", value=generated_desc, key="generated_desc")
                submit = st.form_submit_button("Create Event")
                if submit:
                    user_id = st.session_state.user_id
                    if not user_id:
                        st.error("You must be logged in to add an event.")
                    elif not title or not category or not description:
                        st.error("Title, Category, and Description are required.")
                    else:
                        add_event(title, str(date), venue, description, category, user_id)
                        st.success("Event added successfully!")
                        st.session_state.page = "Home"  # Return to Home after adding an event
                        st.rerun()

        elif st.session_state.page == "Feedback":
            submit_feedback()

        elif st.session_state.page == "Performance Insights":
            analyze_event_performance()

        elif st.session_state.page == "Stall Suggestions":
            recommend_stalls()

        elif st.session_state.page == "Crowd Monitor":
            st.markdown("<h2 class='section-title'>Crowd Monitor</h2>", unsafe_allow_html=True)
            # Session state to track if stall is registered
            if "stall_registered" not in st.session_state:
                st.session_state.stall_registered = False

            # Get user ID
            user_id = st.text_input("User ID", placeholder="Enter your ID")
            is_stall_owner = False
            stall_name = ""
            if not st.session_state.stall_registered:
                is_stall_owner = st.checkbox("I’m a Stall Owner")
                if is_stall_owner:
                    stall_name = st.text_input("Stall Name", placeholder="e.g., Tech Stall")

            # JavaScript for manual location update
            location_script = """
            <script>
            function updateLocation() {
                if (navigator.geolocation) {
                    navigator.geolocation.getCurrentPosition(sendPosition, showError, {
                        enableHighAccuracy: false,  // Reduced accuracy for faster response
                        timeout: 15000,  // 15 seconds timeout
                        maximumAge: 0
                    });
                } else {
                    alert("Geolocation is not supported by this browser.");
                }
            }

            function sendPosition(position) {
                const lat = position.coords.latitude;
                const lon = position.coords.longitude;
                const userId = "%s";  // Insert user_id from Streamlit
                const isStallOwner = %s;  // Insert is_stall_owner from Streamlit (only for first registration)
                const stallName = "%s";  // Insert stall_name from Streamlit (only for first registration)
                const stallRegistered = %s;  // Track if stall is already registered
                
                console.log(`Sending location for user ${userId}: latitude=${lat} (type: ${typeof lat}), longitude=${lon} (type: ${typeof lon})`);
                fetch("%s/save-location", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        user_id: userId,
                        latitude: lat,
                        longitude: lon,
                        is_stall_owner: isStallOwner && !stallRegistered,  // Only true on first call if stall owner
                        stall_name: stallName
                    })
                })
                .then(response => {
                    if (!response.ok) {
                        return response.json().then(err => { throw new Error(err.error); });
                    }
                    return response.json();
                })
                .then(data => {
                    document.getElementById("status").innerText = "Location updated: " + lat.toFixed(6) + ", " + lon.toFixed(6);
                    if (isStallOwner && !stallRegistered) {
                        document.getElementById("updateLocationBtn").disabled = true; // Disable button after registration
                        document.getElementById("stall_registered_flag").value = "true";
                    }
                })
                .catch(error => {
                    document.getElementById("status").innerText = "Error: " + error.message;
                    console.error("Error sending location:", error);
                });
            }

            function showError(error) {
                let message;
                switch(error.code) {
                    case error.PERMISSION_DENIED:
                        message = "User denied the request for Geolocation. Please enable location access.";
                        break;
                    case error.POSITION_UNAVAILABLE:
                        message = "Location information is unavailable. Check your signal or retry.";
                        break;
                    case error.TIMEOUT:
                        message = "The request to get user location timed out. Please try again.";
                        break;
                    case error.UNKNOWN_ERROR:
                        message = "An unknown error occurred. Please try again.";
                        break;
                }
                document.getElementById("status").innerText = "Error: " + message;
                console.error("Geolocation error:", message);
            }
            </script>
            <button id="updateLocationBtn" class="update-button" onclick="updateLocation()">Update Location</button>
            <p id="status">Press 'Update Location' to share your current position.</p>
            <input type="hidden" id="stall_registered_flag" value="false">
            """ % (user_id if user_id else "unknown", "true" if is_stall_owner else "false", stall_name if stall_name else "", "true" if st.session_state.stall_registered else "false", BACKEND_URL)

            # Render the location update script
            if user_id:
                st.components.v1.html(location_script, height=150)
                # Check if stall registration flag was set by JavaScript
                if st.session_state.stall_registered == False:
                    stall_registered_flag = st.components.v1.html('<script>document.write(document.getElementById("stall_registered_flag").value);</script>', height=0)
                    if stall_registered_flag == "true":
                        st.session_state.stall_registered = True
                        st.success("Stall registered successfully! You can no longer update the stall location, but you can update your user position.")
            else:
                st.warning("Please enter a User ID to update location.")

            # Suggest best stall button
            if user_id and st.button("Suggest Best Stall", key="suggest_stall_button", help="Get a recommendation based on crowd and interests", class_="suggest-button"):
                suggest_best_stall(user_id)

            # Check crowd density
            if st.button("Check Crowd Density", key="crowd_density_button"):
                check_crowd_density()

            # Add a note for users
            st.write("**Note:** Location updates require browser permission. Stall positions are fixed after registration; subsequent updates track your user position.")

        elif st.session_state.page == "Admin Dashboard":
            st.markdown("<h2 class='section-title'>Admin Dashboard</h2>", unsafe_allow_html=True)
            password = st.text_input("Admin Password", type="password")
            if password != "admin123":
                st.warning("Incorrect password!")
                return
            df = load_feedback()
            if df.empty:
                st.write("No feedback to display.")
                return
            st.subheader("Feedback Overview")
            selected_stall = st.selectbox("Select Stall", df["stall"].dropna().unique())
            stall_feedback = df[df["stall"] == selected_stall]
            st.write(stall_feedback)
            reply_option = st.radio("Do you want to reply to feedback?", ["No", "Yes"])
            if reply_option == "Yes":
                feedback_options = stall_feedback[stall_feedback["response"].isna() | (stall_feedback["response"] == "")]
                if feedback_options.empty:
                    st.write("No feedback available to reply.")
                    return
                selected_feedback = st.selectbox("Select feedback to reply", feedback_options.index)
                row = df.loc[selected_feedback]
                st.subheader(f"Feedback from {row['name']} ({row['stall']})")
                st.write(row["feedback"])
                response = st.text_area("Your Response")
                if st.button("Submit Response"):
                    df.at[selected_feedback, "response"] = response
                    save_feedback(df)
                    st.success("Response submitted!")
                    st.rerun()
            st.subheader("Delete Feedback")
            delete_option = st.radio("Do you want to delete a feedback?", ["No", "Yes"])
            if delete_option == "Yes":
                delete_feedback = st.selectbox("Select feedback to delete", stall_feedback.index)
                if st.button("Delete Feedback"):
                    df = df.drop(index=delete_feedback)
                    save_feedback(df)
                    st.success("Feedback deleted successfully!")
                    st.rerun()
            st.subheader("Analytics")
            st.write(f"Total feedback received for {selected_stall}: {len(stall_feedback)}")
            rating_counts = stall_feedback["rating"].value_counts().sort_index()
            fig, ax = plt.subplots()
            ax.pie(rating_counts, labels=rating_counts.index, autopct='%1.1f%%', startangle=90, colors=["#ff9999","#66b3ff","#99ff99","#ffcc99","#c2c2f0"])
            ax.axis('equal')
            st.pyplot(fig)
            
            # Add button to extract user IDs and interests to CSV
            if st.button("Export User IDs and Interests to CSV"):
                extract_user_id_interests_to_csv()
                st.success("User IDs and interests exported to user_id_interests.csv!")

if __name__ == "__main__":
    main()