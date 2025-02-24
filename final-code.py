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
from datetime import datetime

# Configure logging for debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Cohere with API key
COHERE_API_KEY = "RF13gvo9zsvPvfJYXz8cXEIylIiGWwkeyJQkxL34"
co = cohere.Client(COHERE_API_KEY)

# Updated categories for events and interests
CATEGORIES = ["Technology", "Music", "Sports", "Art", "Business", "Games", "Movies", "Food", "Products"]

# Mood-to-category mapping
MOOD_MAPPING = {
    "positive": ["Sports", "Music", "Games"],
    "negative": ["Art"],
    "neutral": CATEGORIES
}

# File to store feedback data
FEEDBACK_FILE = "feedback.csv"
USER_LOCATIONS_FILE = "user_locations.csv"
STALLS_FILE = "stalls.csv"

# Flask backend URL
BACKEND_URL = "http://127.0.0.1:5000"

# --- Database Setup ---
def get_db_connection():
    conn = sqlite3.connect('emr.db')
    conn.row_factory = sqlite3.Row  # Access columns by name
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
    cursor.execute('''CREATE TABLE IF NOT EXISTS registrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        event_id INTEGER,
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

# --- Feedback Functions ---
def load_feedback():
    if os.path.exists(FEEDBACK_FILE):
        return pd.read_csv(FEEDBACK_FILE)
    return pd.DataFrame(columns=["name", "feedback", "stall", "rating", "response"])

def save_feedback(df):
    df.to_csv(FEEDBACK_FILE, index=False)

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
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")
        return False

def check_crowd_density():
    try:
        response = requests.get(f"{BACKEND_URL}/crowd_density", timeout=10)
        if response.status_code == 200:
            crowd_data = response.json()
            if "error" in crowd_data:
                st.info(crowd_data["error"])
                return
            else:
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
            st.error("Error fetching crowd density data.")
    except requests.RequestException as e:
        st.error(f"Network error: {str(e)}")
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")

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
        st.error(f"Failed to generate description: {e}")
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
    logger.info(f"Event '{title}' (ID: {event_id}) added by user {created_by}")  # Added logging
    return event_id

def get_all_events():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events ORDER BY id DESC")
    events = cursor.fetchall()
    conn.close()
    logger.info(f"Retrieved {len(events)} events from database")  # Added logging
    return events

def clear_all_events():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM events")
    cursor.execute("DELETE FROM registrations")
    conn.commit()
    conn.close()
    logger.info("All events and registrations cleared from the database.")

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
    if sentiment > 0.3:
        mood = "positive"
    elif sentiment < -0.3:
        mood = "negative"
    else:
        mood = "neutral"
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
    cursor.execute("INSERT INTO registrations (user_id, event_id) VALUES (?, ?)", (user_id, event_id))
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

def display_event(event, show_register=False, show_delete=False, user_id=None, creator_id=None):
    st.write(f"**{event['title']}** 🎉")
    st.write(f"📅 Date: {event['date']}" if event['date'] else "📅 Date not specified")
    st.write(f"📍 Venue: {event['venue']}" if event['venue'] else "📍 Venue not specified")
    st.write(f"🏷️ Category: {event['category']}")
    st.write(event['description'])
    if show_register and user_id:
        if st.button(f"Register for {event['title']}", key=f"reg_{event['id']}"):
            if register_for_event(user_id, event['id']):
                st.success(f"Registered for {event['title']}!")
            else:
                st.warning("You’re already registered for this event.")
    if show_delete and user_id and user_id == creator_id:
        if st.button(f"Delete {event['title']}", key=f"del_{event['id']}"):
            if delete_event(event['id'], user_id):
                st.success(f"Event '{event['title']}' deleted successfully!")
            else:
                st.error("You are not authorized to delete this event.")
    st.write("---")

# --- Feedback and Event Performance Functions ---
def submit_feedback():
    st.title("Submit Feedback")
    name = st.text_input("Your Name")
    feedback = st.text_area("Your Feedback")
    stall = st.selectbox("Select Stall", ["Food Stall", "Tech Stall", "Merchandise Stall", "Game Stall"])
    rating = st.slider("Rate the Stall (1-5)", 1, 5, 3)
    if st.button("Submit"):
        df = load_feedback()
        df = pd.concat([df, pd.DataFrame([{"name": name, "feedback": feedback, "stall": str(stall), "rating": rating, "response": ""}])], ignore_index=True)
        save_feedback(df)
        st.success("Feedback submitted successfully!")

def analyze_event_performance():
    st.title("Event Performance Prediction")
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
    except Exception as e:
        prediction = f"Error fetching prediction: {str(e)}"
    st.subheader(f"Predicted Event Performance for {str(stall_selected)}")
    st.write(prediction)

def recommend_stalls():
    st.title("Stall Recommendations")
    df = load_feedback()
    if df.empty:
        st.write("No feedback available to generate recommendations.")
        return
    user_interest = st.selectbox("Select a stall you are interested in", df["stall"].dropna().unique())
    feedback_text = " ".join(df[df["stall"] == user_interest]["feedback"].dropna().tolist())
    try:
        response = co.generate(
            model="command",
            prompt=f"Based on past feedback and event performance, suggest the best stalls for a user interested in {user_interest}. Feedback data: {feedback_text}"
        )
        recommendation = response.generations[0].text
    except Exception as e:
        recommendation = f"Error fetching recommendation: {str(e)}"
    st.subheader("Recommended Stalls")
    st.write(recommendation)

def admin_dashboard():
    st.title("Admin Dashboard")
    password = st.text_input("Enter Admin Password", type="password")
    if password != "admin123":
        st.warning("Unauthorized access!")
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

# --- Streamlit App with Banner UI ---
def main():
    # Remove or condition this block to avoid clearing events on every run
    # if os.path.exists('emr.db'):
    #     clear_all_events()  # Commented out to preserve events
    initialize_csv()
    init_db()

    st.markdown("""
        <style>
            .banner {
                background-color: #1a1a1a;
                padding: 10px 0;
                margin-bottom: 20px;
            }
            .banner button {
                background-color: #333;
                color: white;
                border: none;
                padding: 10px 20px;
                margin: 0 5px;
                border-radius: 5px;
                font-size: 16px;
                cursor: pointer;
                width: 140px;
                height: 40px;
            }
            .banner button:hover {
                background-color: #555;
            }
            .stTitle {
                color: white;
                text-align: center;
            }
            .crowd-level {
                padding: 10px;
                margin: 5px;
                border-radius: 5px;
                display: flex;
                align-items: center;
                justify-content: space-between;
            }
            .very-low { background-color: #e0f7e9; color: #006400; }
            .low { background-color: #b3e6b3; color: #006400; }
            .medium { background-color: #fff9e6; color: #8b4513; }
            .high { background-color: #ffe6e6; color: #ff4500; }
            .very-high { background-color: #ffcccc; color: #ff0000; }
            .crowd-icon { margin-right: 10px; font-size: 20px; }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="banner">', unsafe_allow_html=True)
    st.markdown('<h1 class="stTitle">Event Management Redefined</h1>', unsafe_allow_html=True)

    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Choose a Page", [
        "Home", "Registration", "All Events", "My Events", "Recommendations", "Add Event",
        "Submit Feedback", "Event Performance Prediction", "Stall Recommendations", "Stall Crowd Monitor", "Admin Dashboard"
    ])

    if 'user_id' not in st.session_state:
        st.session_state.user_id = None

    if page == "Home":
        st.header("Welcome to Event Management Redefined!")
        st.write("Redefining event management with AI-powered recommendations, feedback, and smart tools.")
        st.subheader("Log In")
        user_id = st.number_input("Enter your User ID", min_value=1, step=1)
        if st.button("Log In"):
            user = get_user(user_id)
            if user:
                st.session_state.user_id = user_id
                st.success(f"Logged in as {user['name']}!")
            else:
                st.error("Invalid User ID. Please register first.")
        if st.button("Not registered yet? Click here to register"):
            page = "Registration"
        st.subheader("Featured Events")
        events = get_all_events()
        if events:
            st.write("Check out our latest and most exciting events!")
            for event in events[:3]:
                display_event(event, show_register=True, user_id=st.session_state.user_id, creator_id=event['created_by'])
        else:
            st.write("No featured events available yet.")

    elif page == "Registration":
        st.header("User Registration")
        with st.form("user_form"):
            name = st.text_input("Name")
            email = st.text_input("Email")
            interests = st.multiselect("Select your interests", CATEGORIES)
            submit_register = st.form_submit_button("Register")
            if submit_register:
                if not name or not email or not interests:
                    st.error("All fields are required to register.")
                else:
                    user_id = add_user(name, email, interests)
                    st.success(f"Registered successfully! Your User ID is {user_id}. Return to the Home page to log in.")
                    st.session_state.user_id = user_id

    elif page == "All Events":
        st.header("All Upcoming Events")
        events = get_all_events()
        if events:
            for event in events:
                display_event(event, show_register=True, show_delete=True, user_id=st.session_state.user_id, creator_id=event['created_by'])
        else:
            st.write("No events available yet.")

    elif page == "My Events":
        st.header("My Registered Events")
        if not st.session_state.user_id:
            st.warning("Please log in first.")
        else:
            registrations = get_user_registrations(st.session_state.user_id)
            if registrations:
                for event in registrations:
                    display_event(event, show_delete=True, user_id=st.session_state.user_id, creator_id=event['created_by'])
            else:
                st.write("You haven’t registered for any events yet.")

    elif page == "Recommendations":
        st.header("Personalized Recommendations")
        if not st.session_state.user_id:
            st.warning("Please log in first.")
        else:
            st.subheader("Based on Your Interests")
            interest_events = get_interest_based_events(st.session_state.user_id)
            if interest_events:
                for event in interest_events:
                    display_event(event, show_register=True, user_id=st.session_state.user_id, creator_id=event['created_by'])
            else:
                st.write("No interest-based recommendations yet. Update your interests on the Registration page!")
            st.subheader("Based on Your Mood")
            mood_input = st.text_input("How are you feeling today? (e.g., 'I’m excited' or 'I’m stressed')")
            if mood_input:
                mood_events = get_mood_based_events(mood_input)
                if mood_events:
                    for event in mood_events:
                        display_event(event, show_register=True, user_id=st.session_state.user_id, creator_id=event['created_by'])
                else:
                    st.write("No mood-based events available right now.")
            else:
                st.write("Enter your mood to see tailored recommendations.")

    elif page == "Add Event":
        st.header("Add a New Event")
        with st.form("event_form"):
            title = st.text_input("Event Title", value="")
            date = st.text_input("Date (e.g., 2025-02-25 or YYYY-MM-DD)", value="", help="Optional: Leave blank if not applicable")
            venue = st.text_input("Venue", value="", help="Optional: Leave blank if not applicable")
            description = st.text_area("Description", value="")
            category = st.selectbox("Category", CATEGORIES)
            generate_desc = st.checkbox("Generate AI Description")
            submit = st.form_submit_button("Add Event")

            if generate_desc:
                if not title or not category:
                    st.error("Please fill in Title and Category to generate a description.")
                else:
                    description = generate_event_description(title, category, date, venue)
                    st.text_area("Generated Description", value=description, key="generated_desc")

            if submit:
                user_id = st.session_state.user_id
                if not user_id:
                    st.error("You must be logged in to add an event.")
                elif not title or not category or not description:
                    st.error("Title, Category, and Description are required to add an event.")
                else:
                    add_event(title, date, venue, description, category, user_id)
                    st.success("Event added successfully!")
                    st.rerun()  # Refresh the app to update "All Events"

    elif page == "Submit Feedback":
        submit_feedback()

    elif page == "Event Performance Prediction":
        analyze_event_performance()

    elif page == "Stall Recommendations":
        recommend_stalls()

    elif page == "Stall Crowd Monitor":
        st.title("Stall Crowd Monitor")
        user_id = st.text_input("Enter your User ID:", key="user_id")
        is_stall_owner = st.checkbox("I am a stall owner", key="stall_owner")
        stall_name = ""
        if is_stall_owner:
            stall_name = st.text_input("Enter your Stall Name:", key="stall_name")
        col1, col2 = st.columns(2)
        with col1:
            latitude = st.number_input("Enter Latitude:", format="%.6f", key="latitude")
        with col2:
            longitude = st.number_input("Enter Longitude:", format="%.6f", key="longitude")
        if st.button("Share Location"):
            if share_location(user_id, latitude, longitude, is_stall_owner, stall_name):
                st.rerun()
        if st.button("Check Crowd Density"):
            check_crowd_density()
        st.write("**Note:** Use Google Maps or another mapping tool to find your latitude and longitude.")

    elif page == "Admin Dashboard":
        admin_dashboard()

if __name__ == "__main__":
    main()
