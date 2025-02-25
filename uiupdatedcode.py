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
from streamlit_option_menu import option_menu
from streamlit_folium import folium_static
import folium

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cohere API setup
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
            st.error("Error fetching crowd density data.")
    except requests.RequestException as e:
        st.error(f"Network error: {str(e)}")

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

# --- UI Display Function (Updated for Better Visibility and Color) ---
def display_event(event, show_register=False, show_delete=False, user_id=None, creator_id=None):
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
                if st.button("Register", key=f"reg_{event['id']}"):
                    if register_for_event(user_id, event['id']):
                        st.success(f"Registered for {event['title']}!")
                    else:
                        st.warning("You’re already registered for this event.")
            if show_delete and user_id and user_id == creator_id:
                if st.button("Delete", key=f"del_{event['id']}"):
                    if delete_event(event['id'], user_id):
                        st.success(f"Event '{event['title']}' deleted successfully!")
                        st.rerun()
                    else:
                        st.error("You are not authorized to delete this event.")

# --- Streamlit App ---
def main():
    initialize_csv()
    init_db()

    # Custom CSS for UI (Updated for better event card visibility and color)
    st.markdown("""
        <style>
            .main { background-color: #f5f5f5; padding: 20px; border-radius: 10px; }
            .stButton>button { background-color: #4CAF50; color: white; border-radius: 5px; padding: 10px 20px; font-size: 14px; }
            .stButton>button:hover { background-color: #45a049; }
            .sidebar .sidebar-content { background-color: #2c3e50; color: white; }
            .sidebar h2 { color: #ecf0f1; }
            .event-card { 
                background-color: #000000;  /* Black background for event cards */
                padding: 20px; 
                margin-bottom: 20px; 
                border-radius: 15px; 
                box-shadow: 0 4px 10px rgba(0,0,0,0.1); 
                max-width: 100%; 
                overflow: auto; 
                word-wrap: break-word; 
            }
            .header { color: #2c3e50; font-family: 'Arial', sans-serif; }
            .banner { background: #00b4d8; padding: 20px; text-align: center; color: white; border-radius: 10px; margin-bottom: 20px; } /* Bright teal banner */
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
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="banner"><h1>EventHub</h1><p>Your All-in-One Event Experience</p></div>', unsafe_allow_html=True)

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

    if 'user_id' not in st.session_state:
        st.session_state.user_id = None

    with st.container():
        if page == "Home":
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
            st.button("New User? Register Here", key="to_register")
            st.markdown("<h3>Featured Events</h3>", unsafe_allow_html=True)
            events = get_all_events()
            if events:
                st.write("Explore our top picks!")
                for event in events[:3]:
                    display_event(event, show_register=True, user_id=st.session_state.user_id, creator_id=event['created_by'])
            else:
                st.write("No events available yet.")

        elif page == "Register":
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

        elif page == "All Events":
            st.markdown("<h2 class='section-title'>Upcoming Events</h2>", unsafe_allow_html=True)
            st.write("Browse all events happening soon.")
            events = get_all_events()
            if events:
                for event in events:
                    display_event(event, show_register=True, show_delete=True, user_id=st.session_state.user_id, creator_id=event['created_by'])
            else:
                st.write("No events available yet.")

        elif page == "My Events":
            st.markdown("<h2 class='section-title'>My Events</h2>", unsafe_allow_html=True)
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
            st.markdown("<h2 class='section-title'>Tailored for You</h2>", unsafe_allow_html=True)
            if not st.session_state.user_id:
                st.warning("Please log in first.")
            else:
                tab1, tab2 = st.tabs(["Interest-Based Picks", "Mood-Based Suggestions"])
                with tab1:
                    st.subheader("Based on Your Interests")
                    interest_events = get_interest_based_events(st.session_state.user_id)
                    if interest_events:
                        for event in interest_events:
                            display_event(event, show_register=True, user_id=st.session_state.user_id, creator_id=event['created_by'])
                    else:
                        st.write("No interest-based recommendations yet.")
                with tab2:
                    st.subheader("Based on Your Mood")
                    mood_input = st.text_input("How are you feeling today?", placeholder="Happy, sad, excited...")
                    if mood_input:
                        mood_events = get_mood_based_events(mood_input)
                        if mood_events:
                            for event in mood_events:
                                display_event(event, show_register=True, user_id=st.session_state.user_id, creator_id=event['created_by'])
                        else:
                            st.write("No mood-based events available right now.")
                    else:
                        st.write("Enter your mood to see recommendations!")

        elif page == "Add Event":
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
                        st.rerun()

        elif page == "Feedback":
            submit_feedback()

        elif page == "Performance Insights":
            analyze_event_performance()

        elif page == "Stall Suggestions":
            recommend_stalls()

        elif page == "Crowd Monitor":
            st.markdown("<h2 class='section-title'>Crowd Monitor</h2>", unsafe_allow_html=True)
            user_id = st.text_input("User ID", placeholder="Enter your ID")
            is_stall_owner = st.checkbox("I’m a Stall Owner")
            stall_name = st.text_input("Stall Name", placeholder="e.g., Tech Stall") if is_stall_owner else ""
            col1, col2 = st.columns(2)
            with col1:
                latitude = st.number_input("Latitude", format="%.6f")
            with col2:
                longitude = st.number_input("Longitude", format="%.6f")
            col3, col4 = st.columns(2)
            with col3:
                if st.button("Share Location"):
                    share_location(user_id, latitude, longitude, is_stall_owner, stall_name)
            with col4:
                if st.button("Check Crowd"):
                    check_crowd_density()
            st.subheader("Location Map")
            m = folium.Map(location=[latitude if latitude else 37.7749, longitude if longitude else -122.4194], zoom_start=12)
            if latitude and longitude:
                folium.Marker([latitude, longitude], popup=stall_name or f"User {user_id}", icon=folium.Icon(color="blue")).add_to(m)
            folium_static(m, width=600, height=400)

        elif page == "Admin Dashboard":
            admin_dashboard()

if __name__ == "__main__":
    main()