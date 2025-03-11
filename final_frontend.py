import sqlite3
import streamlit as st
import pandas as pd
import os
import requests
from textblob import TextBlob
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from datetime import datetime, timedelta
from streamlit_option_menu import option_menu
from streamlit_folium import folium_static
import folium
import math
import csv
from groq import Groq
import logging
import tempfile
import json
import time
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

# Configure logging
logging.basicConfig(level=logging.INFO, filename='app.log', filemode='a', format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# API setup with your Groq API key
GROQ_API_KEY = "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"
co = Groq(api_key=GROQ_API_KEY)

# Constants
CATEGORIES = ["Technology", "Music", "Sports", "Art", "Business", "Games", "Movies", "Food", "Products"]
MOOD_MAPPING = {"positive": ["Sports", "Music", "Games"], "negative": ["Art"], "neutral": CATEGORIES}
FEEDBACK_FILE = "feedback.csv"
USER_LOCATIONS_FILE = "user_locations.csv"
STALLS_FILE = "stalls.csv"
BACKEND_URL = "http://127.0.0.1:5000"
STALLS = ["Food Stall", "Tech Stall", "Merchandise Stall", "Game Stall"]

# Database connection
def get_db_connection():
    conn = sqlite3.connect('emr.db')
    conn.row_factory = sqlite3.Row
    return conn

# Initialize database
def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            interests TEXT
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS events (
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
            registration_date TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (event_id) REFERENCES events(id)
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS stalls (
            user_id INTEGER PRIMARY KEY,
            stall_name TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS user_locations (
            user_id INTEGER PRIMARY KEY,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            timestamp TEXT NOT NULL
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS stall_categories (
            stall_name TEXT PRIMARY KEY,
            category TEXT
        )''')
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        st.error(f"Database initialization failed: {str(e)}")

# CSV Initialization
def initialize_csv():
    try:
        if not os.path.exists(FEEDBACK_FILE):
            pd.DataFrame(columns=["name", "feedback", "event", "rating", "response"]).to_csv(FEEDBACK_FILE, index=False)
            logger.info("Initialized feedback CSV file.")
        if not os.path.exists("user_interests.csv"):
            pd.DataFrame(columns=["id", "name", "email", "interests"]).to_csv("user_interests.csv", index=False)
            logger.info("Initialized user interests CSV file.")
        if not os.path.exists("user_id_interests.csv"):
            pd.DataFrame(columns=["id", "interests"]).to_csv("user_id_interests.csv", index=False)
            logger.info("Initialized user ID and interests CSV file.")
        if not os.path.exists("stall_people_count.csv"):
            pd.DataFrame(columns=["stall_name", "people_count"]).to_csv("stall_people_count.csv", index=False)
            logger.info("Initialized stall people count CSV file.")
        if not os.path.exists(STALLS_FILE):
            pd.DataFrame(columns=["user_id", "stall_name", "latitude", "longitude"]).to_csv(STALLS_FILE, index=False)
            logger.info("Initialized stalls CSV file.")
        if not os.path.exists(USER_LOCATIONS_FILE):
            pd.DataFrame(columns=["user_id", "latitude", "longitude", "timestamp"]).to_csv(USER_LOCATIONS_FILE, index=False)
            logger.info("Initialized user_locations CSV file.")
    except Exception as e:
        logger.error(f"Error initializing CSV files: {str(e)}")
        st.error(f"CSV initialization failed: {str(e)}")

# Proxy function to forward requests to the backend
@st.cache_data(show_spinner="Processing backend request...")
def proxy_to_backend(endpoint, method="POST", json_data=None):
    backend_url = f"{BACKEND_URL}{endpoint}"
    try:
        if method == "POST":
            logger.debug(f"Sending to backend: {json_data}")
            response = requests.post(backend_url, json=json_data, timeout=5)
        else:
            response = requests.get(backend_url, params=json_data, timeout=5)
        response.raise_for_status()
        logger.debug(f"Received from backend: {response.text}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Proxy error: {str(e)}")
        st.error(f"Proxy error: {str(e)}")
        return {"error": str(e)}

# Function to save location data to the backend
def share_location(user_id, lat, lon, is_stall_owner, stall_name=None):
    try:
        response = proxy_to_backend(
            "/save-location",
            method="POST",
            json_data={
                "user_id": user_id,
                "latitude": lat,
                "longitude": lon,
                "is_stall_owner": is_stall_owner,
                "stall_name": stall_name
            }
        )
        if "error" in response:
            st.error(f"Failed to save location: {response['error']}")
            return False
        st.success("Location updated")
        return True
    except Exception as e:
        logger.error(f"Failed to save location: {str(e)}")
        st.error(f"Failed to save location: {str(e)}")
        return False

# Fallback function to get location using ip-api.com
def get_fallback_location():
    try:
        response = requests.get("http://ip-api.com/json", timeout=5)
        data = response.json()
        if data["status"] == "success":
            st.write(f'<script>console.log("Fallback to IP-based location successful: lat={data["lat"]}, lon={data["lon"]} (accuracy ~2000m)");</script>', unsafe_allow_html=True)
            return data["lat"], data["lon"]
        else:
            st.write('<script>console.log("Fallback to IP-based location failed: API returned status failure");</script>', unsafe_allow_html=True)
            return None, None
    except Exception as e:
        logger.error(f"Fallback geolocation error: {str(e)}")
        st.write('<script>console.log("Fallback to IP-based location failed");</script>', unsafe_allow_html=True)
        return None, None

# Feedback Functions
def load_feedback():
    if os.path.exists(FEEDBACK_FILE):
        return pd.read_csv(FEEDBACK_FILE)
    return pd.DataFrame(columns=["name", "feedback", "event", "rating", "response"])

def save_feedback(df):
    df.to_csv(FEEDBACK_FILE, index=False)

# Database Utility Functions
def get_all_events():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events ORDER BY id DESC")
    events = cursor.fetchall()
    conn.close()
    return events

def get_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_stall_crowd_density():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.stall_name, s.latitude, s.longitude, COUNT(ul.user_id) as crowd_count
        FROM stalls s
        LEFT JOIN user_locations ul ON (
            (ul.latitude - s.latitude) * (ul.latitude - s.latitude) + 
            (ul.longitude - s.longitude) * (ul.longitude - s.longitude)
        ) <= (0.0005 * 0.0005)  -- Approx 50 meters in degrees
        GROUP BY s.stall_name, s.latitude, s.longitude
    """)
    crowd_data = {row["stall_name"]: {"latitude": row["latitude"], "longitude": row["longitude"], "crowd_count": row["crowd_count"] or 0} for row in cursor.fetchall()}
    conn.close()
    return crowd_data

# Enhanced check_crowd_density with Folium map
def check_crowd_density():
    if not st.session_state.user_id or st.session_state.user_id == "unknown":
        st.error("Error: User ID is required to check crowd density.")
        return

    try:
        # Fetch crowd data from backend or local database
        params = {"user_id": st.session_state.user_id}
        if st.session_state.get("last_location"):
            lat, lon = map(float, st.session_state.last_location.strip("()").split(","))
            params.update({"latitude": lat, "longitude": lon})

        response = proxy_to_backend("/crowd_density", method="GET", json_data=params)
        crowd_data = response if "error" not in response else get_stall_crowd_density()

        # Create a Folium map
        user_lat = lat if st.session_state.get("last_location") else 37.7749  # Default to San Francisco if no user location
        user_lon = lon if st.session_state.get("last_location") else -122.4194
        m = folium.Map(location=[user_lat, user_lon], zoom_start=13)

        # Add user location marker
        if st.session_state.get("last_location"):
            folium.Marker(
                [user_lat, user_lon],
                popup="Your Location",
                icon=folium.Icon(color="green", icon="user")
            ).add_to(m)

        # Add stall markers with crowd density
        for stall_name, details in crowd_data.items():
            if isinstance(details, dict) and "latitude" in details and "longitude" in details and "crowd_count" in details:
                crowd_count = details["crowd_count"]
                color = "green" if crowd_count < 10 else "orange" if crowd_count < 20 else "red"
                popup_text = f"{stall_name}<br>Crowd Count: {crowd_count}"
                folium.Marker(
                    [details["latitude"], details["longitude"]],
                    popup=popup_text,
                    icon=folium.Icon(color=color, icon="info-sign")
                ).add_to(m)

        # Display the map
        folium_static(m)

        # Additional crowd density details
        if st.session_state.get("stall_registered", False) and st.session_state.get("stall_name"):
            stall_name = st.session_state.stall_name
            if stall_name in crowd_data:
                details = crowd_data[stall_name]
                st.success(f"Crowd Density for {stall_name}:")
                st.write(f"People Count: {details['crowd_count']}")
                st.write(f"Crowd Level: {'Low' if details['crowd_count'] < 10 else 'Medium' if details['crowd_count'] < 20 else 'High'}")
                st.write(f"Location: ({details['latitude']:.6f}, {details['longitude']:.6f})")
                chart_data = pd.DataFrame({"Stall": [stall_name], "People Count": [details["crowd_count"]]})
                st.bar_chart(chart_data.set_index("Stall"))
            else:
                st.warning(f"No crowd data available for your stall ({stall_name}).")
        else:
            if st.session_state.get("last_location"):
                nearby_stalls = {}
                for stall_name, details in crowd_data.items():
                    if isinstance(details, dict) and "latitude" in details and "longitude" in details:
                        distance = geodesic((user_lat, user_lon), (details["latitude"], details["longitude"])).meters
                        if distance <= 50:
                            nearby_stalls[stall_name] = details
                if nearby_stalls:
                    st.success("Crowd Density for Nearby Stalls:")
                    chart_data = pd.DataFrame({
                        "Stall": list(nearby_stalls.keys()),
                        "People Count": [details["crowd_count"] for details in nearby_stalls.values()]
                    })
                    st.bar_chart(chart_data.set_index("Stall"))
                    for stall_name, details in nearby_stalls.items():
                        st.write(f"- {stall_name}:")
                        st.write(f"  People Count: {details['crowd_count']}")
                        st.write(f"  Crowd Level: {'Low' if details['crowd_count'] < 10 else 'Medium' if details['crowd_count'] < 20 else 'High'}")
                        st.write(f"  Location: ({details['latitude']:.6f}, {details['longitude']:.6f})")
                else:
                    st.info("No stalls within 50 meters of your location.")
            else:
                st.info("Please update your location to see nearby crowd density.")

    except Exception as e:
        logger.error(f"Error checking crowd density: {str(e)}")
        st.error(f"Error fetching crowd density: {str(e)}")

# Chatbot Functions
def get_eventbuddy_response(user_input, user_id, conversation_history):
    system_prompt = """
    You are EventBuddy, a cheerful and helpful AI assistant for EventHub, created by xAI. Your goal is to assist users with a friendly, witty vibe, just like Grok! Tasks include:
    1. Register users for events (use register_for_event).
    2. Create events (use add_event with title, date, venue, description, category).
    3. Provide stall feedback (use load_feedback).
    4. Recommend events or stalls based on interests (use get_interest_based_events or recommend_stalls).
    5. Check crowd density for stalls (use check_crowd_density or get_stall_crowd_density).
    Respond naturally, offer clarifications, and use [FETCH_DATA] for dynamic data.
    """
    history = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history:
        history.append({"role": msg["role"], "content": msg["message"]})
    history.append({"role": "user", "content": user_input})

    try:
        response = co.chat.completions.create(
            model="llama3-8b-8192",
            messages=history,
            max_tokens=150,
            temperature=0.7
        )
        assistant_response = response.choices[0].message.content.strip()
        logger.info("Successfully fetched response from Groq API.")
    except Exception as e:
        logger.error(f"Groq API error: {str(e)}")
        return f"Oops! Couldn’t connect to the Groq API. Error: {str(e)}"

    return assistant_response

# Other Utility Functions
def add_user(name, email, interests):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (name, email, interests) VALUES (?, ?, ?)",
                   (name, email, ",".join(interests)))
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    
    user_data = pd.DataFrame([{"id": user_id, "name": name, "email": email, "interests": ",".join(interests)}])
    if os.path.exists("user_interests.csv"):
        existing_data = pd.read_csv("user_interests.csv")
        updated_data = pd.concat([existing_data, user_data], ignore_index=True)
    else:
        updated_data = user_data
    updated_data.to_csv("user_interests.csv", index=False)
    
    user_id_interests = pd.DataFrame([{"id": user_id, "interests": ",".join(interests)}])
    if os.path.exists("user_id_interests.csv"):
        existing_id_data = pd.read_csv("user_id_interests.csv")
        updated_id_data = pd.concat([existing_id_data, user_id_interests], ignore_index=True)
    else:
        updated_id_data = user_id_interests
    updated_id_data.to_csv("user_id_interests.csv", index=False)
    
    logger.info(f"User interests for {name} (ID: {user_id}) saved to SQLite and CSV files.")
    return user_id

def add_event(title, date, venue, description, category, created_by):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO events (title, date, venue, description, category, created_by) VALUES (?, ?, ?, ?, ?, ?)",
                   (title, date, venue, description, category, created_by))
    conn.commit()
    event_id = cursor.lastrowid
    conn.close()
    
    csv_file = "events.csv"
    file_exists = os.path.isfile(csv_file)
    with open(csv_file, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["event_id", "title", "date", "venue", "description", "category", "created_by"])
        writer.writerow([event_id, title, date, venue, description, category, created_by])
    
    logger.info(f"Event '{title}' (ID: {event_id}) added by user {created_by} to database and CSV file")
    return event_id

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

def suggest_best_stall(user_id):
    try:
        response = requests.post(f"{BACKEND_URL}/suggest_stall", json={"user_id": user_id}, timeout=10)
        if response.status_code == 200:
            suggestion = response.json()
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

# Streamlit App
def main():
    print("Starting Streamlit app...")
    try:
        initialize_csv()
        init_db()
    except Exception as e:
        logger.error(f"Error during initialization: {str(e)}")
        st.error(f"Initialization failed: {str(e)}")
        return

    # Initialize session state variables
    if 'page' not in st.session_state:
        st.session_state.page = "Home"
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
    if 'conversation_history' not in st.session_state:
        st.session_state.conversation_history = []
    if 'stall_registered' not in st.session_state:
        st.session_state.stall_registered = False
    if 'stall_name' not in st.session_state:
        st.session_state.stall_name = None
    if 'is_stall_owner' not in st.session_state:
        st.session_state.is_stall_owner = False

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
            .chat-container { background-color: #1a1a1a; padding: 20px; border-radius: 10px; max-height: 500px; overflow-y: auto; }
            .message-bubble { padding: 10px 15px; margin: 5px 0; border-radius: 10px; max-width: 70%; }
            .user-message { background-color: #4CAF50; color: white; align-self: flex-end; }
            .bot-message { background-color: #3498db; color: white; align-self: flex-start; }
            .query-options { margin-top: 10px; }
            .query-options button { background-color: #3498db; color: white; border: none; padding: 8px 15px; margin: 5px; border-radius: 5px; cursor: pointer; }
            .query-options button:hover { background-color: #2980b9; }
            .crowd-level { padding: 10px; margin: 5px; border-radius: 5px; display: flex; align-items: center; justify-content: space-between; }
            .very-low { background-color: #e0f7e9; color: #006400; }
            .low { background-color: #b3e6b3; color: #006400; }
            .medium { background-color: #fff9e6; color: #8b4513; }
            .high { background-color: #ffe6e6; color: #ff4500; }
            .very-high { background-color: #ffcccc; color: #ff0000; }
            .crowd-icon { margin-right: 10px; font-size: 20px; }
            .update-button {
                background: linear-gradient(45deg, #6ab7f5, #1e90ff);
                color: white;
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                font-size: 16px;
                font-weight: bold;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                transition: all 0.3s ease;
                box-shadow: 0 4px 15px rgba(0, 123, 255, 0.3);
                margin-right: 10px;
            }
            .update-button i {
                margin-right: 8px;
            }
            .update-button:hover {
                background: linear-gradient(45deg, #1e90ff, #6ab7f5);
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(0, 123, 255, 0.5);
            }
            .update-button:active {
                transform: translateY(1px);
                box-shadow: 0 2px 10px rgba(0, 123, 255, 0.2);
            }
            .update-button:disabled {
                background: #cccccc;
                cursor: not-allowed;
                box-shadow: none;
                transform: none;
            }
            .suggest-button { background-color: #2196F3; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; margin-right: 10px; transition: background-color 0.3s; }
            .suggest-button:hover { background-color: #1976D2; }
            .suggestion-message { background-color: #e8f5e9; color: #2e7d32; padding: 12px 15px; border-radius: 5px; margin-top: 10px; font-size: 16px; border-left: 4px solid #4CAF50; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); }
            .location-info { color: #2c3e50; font-weight: bold; margin-top: 10px; }
        </style>
        <!-- Include Font Awesome for icons -->
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    """, unsafe_allow_html=True)

    st.markdown('<div class="banner"><h1>Event Management Redefined</h1><p>Redefining your experience</p></div>', unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("<h2>Explore EventHub</h2>", unsafe_allow_html=True)
        page = option_menu(
            menu_title=None,
            options=["Home", "Register", "All Events", "My Events", "Recommendations", "Add Event", "Feedback", "Performance Insights", "Stall Suggestions", "Crowd Monitor", "Admin Dashboard", "Chatbot"],
            icons=["house", "person-plus", "calendar", "bookmark", "lightbulb", "plus-circle", "chat", "graph-up", "shop", "people", "shield-lock", "robot"],
            default_index=0,
            styles={
                "container": {"padding": "0!important", "background-color": "#2c3e50"},
                "icon": {"color": "#ecf0f1", "font-size": "18px"},
                "nav-link": {"color": "#ecf0f1", "font-size": "16px", "text-align": "left", "margin": "0px", "--hover-color": "#3498db"},
                "nav-link-selected": {"background-color": "#3498db"},
            }
        )
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
                st.session_state.page = "Register"
                st.rerun()
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
                        st.session_state.page = "Home"
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
                        st.session_state.page = "Home"
                        st.rerun()

        elif st.session_state.page == "Feedback":
            st.markdown("<h2 class='section-title'>Share Your Feedback</h2>", unsafe_allow_html=True)
            name = st.text_input("Your Name", placeholder="Enter your name")
            feedback = st.text_area("Feedback", placeholder="What did you think?")
            events = [e["title"] for e in get_all_events()] + STALLS
            event = st.selectbox("Event or Stall", events)
            rating = st.slider("Rating", 1, 5, 3, help="Rate from 1 (poor) to 5 (excellent)")
            if st.button("Submit Feedback"):
                df = load_feedback()
                df = pd.concat([df, pd.DataFrame([{"name": name, "feedback": feedback, "event": str(event), "rating": rating, "response": ""}])], ignore_index=True)
                save_feedback(df)
                st.success("Feedback submitted successfully!")
                logger.info(f"Feedback submitted for {event} by {name}")

        elif st.session_state.page == "Performance Insights":
            st.markdown("<h2 class='section-title'>Event Insights</h2>", unsafe_allow_html=True)
            df = load_feedback()
            if df.empty:
                st.write("No feedback available.")
                return
            stall_selected = st.selectbox("Select event or stall to Analyze", df["event"].dropna().unique())
            stall_feedback = df[df["event"] == stall_selected]
            feedback_text = " ".join(stall_feedback["feedback"].dropna().tolist())
            try:
                response = co.chat.completions.create(
                    model="llama3-8b-8192",
                    messages=[
                        {"role": "system", "content": "You are an analyst summarizing event performance based on feedback."},
                        {"role": "user", "content": f"Analyze feedback for {stall_selected} and summarize event performance: {feedback_text}"}
                    ]
                )
                prediction = response.choices[0].message.content
                logger.info(f"Generated performance prediction for {stall_selected}")
            except Exception as e:
                prediction = f"Error fetching prediction: {str(e)}"
                logger.error(f"Groq error in performance prediction: {str(e)}")
            st.subheader(f"Predicted Performance for {stall_selected}")
            st.write(prediction)

        elif st.session_state.page == "Stall Suggestions":
            st.markdown("<h2 class='section-title'>Event Recommendations</h2>", unsafe_allow_html=True)
            df = load_feedback()
            if df.empty:
                st.write("No feedback available to generate recommendations.")
                return
            user_interest = st.selectbox("Select an event or stall you are interested in", df["event"].dropna().unique())
            feedback_text = " ".join(df[df["event"] == user_interest]["feedback"].dropna().tolist())
            if not feedback_text:
                st.write(f"No feedback available for {user_interest} to generate recommendations.")
                return
            try:
                response = co.chat.completions.create(
                    model="llama3-8b-8192",
                    messages=[
                        {"role": "system", "content": "You are a recommendation system suggesting stalls based on event feedback."},
                        {"role": "user", "content": f"Based on past feedback and event performance, suggest the best stalls for a user interested in {user_interest}. Feedback data: {feedback_text}"}
                    ]
                )
                recommendation = response.choices[0].message.content
                logger.info(f"Generated stall recommendation for interest: {user_interest}")
            except Exception as e:
                recommendation = f"Error fetching recommendation: {str(e)}"
                logger.error(f"Groq error in stall recommendation: {str(e)}")
            st.subheader("Recommended Event")
            st.write(recommendation)

        elif st.session_state.page == "Crowd Monitor":
            st.markdown("<h2 class='section-title'>Crowd Monitor</h2>", unsafe_allow_html=True)
            st.session_state.user_id = st.text_input("User ID", placeholder="Enter your ID", value=str(st.session_state.user_id) if st.session_state.user_id else "", key="crowd_monitor_user_id")

            if st.session_state.user_id:
                if st.button("Update Location", key="update_location_button"):
                    if not st.session_state.user_id or st.session_state.user_id == "unknown":
                        st.error("Error: User ID is required.")
                    else:
                        st.session_state["geo_data"] = None
                        location_script = """
                        <script>
                        let retryCount = 0;
                        const MAX_RETRIES = 3;
                        const TIMEOUT = 10000;
                        const ACCURACY_THRESHOLD = 1000;

                        function checkPermissionsAndGetLocation() {
                            console.log("Initiating geolocation request...");
                            navigator.permissions.query({ name: "geolocation" }).then((result) => {
                                if (result.state === "denied") {
                                    console.error("Location permission denied. Please enable in browser settings and ensure Wi-Fi is on.");
                                    window.parent.postMessage({ type: "geolocation", data: "Error: Location permission denied. Please enable in browser settings and ensure Wi-Fi is on." }, "*");
                                    return;
                                }
                                console.log("Location permission state: " + result.state);
                                getLocation();
                            }).catch((error) => {
                                console.error("Permission check error: " + error);
                                window.parent.postMessage({ type: "geolocation", data: "Error: Unable to check permissions - " + error }, "*");
                            });
                        }

                        function getLocation() {
                            if (!navigator.geolocation) {
                                console.error("Geolocation not supported by browser");
                                window.parent.postMessage({ type: "geolocation", data: "Error: Geolocation not supported by browser" }, "*");
                                return;
                            }
                            console.log("Attempting to fetch location via Wi-Fi triangulation (Retry " + (retryCount + 1) + "/5)...");
                            navigator.geolocation.getCurrentPosition(
                                (position) => {
                                    const lat = position.coords.latitude;
                                    const lon = position.coords.longitude;
                                    const accuracy = position.coords.accuracy || 0;
                                    const source = accuracy <= ACCURACY_THRESHOLD ? "Wi-Fi Triangulation" : "IP Triangulation";
                                    console.log(`Geolocation attempt ${retryCount + 1}: lat=${lat}, lon=${lon}, accuracy=${accuracy}m, source=${source}`);
                                    if (accuracy > ACCURACY_THRESHOLD && retryCount < MAX_RETRIES) {
                                        retryCount++;
                                        console.log(`Accuracy too low (${accuracy}m). Retrying (${retryCount}/${MAX_RETRIES})...`);
                                        setTimeout(getLocation, 3000);
                                    } else {
                                        if (accuracy > ACCURACY_THRESHOLD) {
                                            console.log("Max retries reached with low accuracy. Will fall back to IP-based location.");
                                        } else {
                                            console.log("Geolocation successful after " + (retryCount + 1) + " attempt(s).");
                                        }
                                        window.parent.postMessage({ type: "geolocation", data: { lat: lat, lon: lon, accuracy: accuracy, source: source } }, "*");
                                    }
                                },
                                (error) => {
                                    console.error(`Geolocation Error (Retry ${retryCount + 1}/5): Code ${error.code} - ${error.message}`);
                                    if ((error.code === 3 || error.code === 2) && retryCount < MAX_RETRIES) {
                                        retryCount++;
                                        console.log(`Retrying due to error (${retryCount}/${MAX_RETRIES})...`);
                                        setTimeout(getLocation, 3000);
                                    } else {
                                        console.log(`Failed to get Wi-Fi triangulation after ${MAX_RETRIES} retries. Will fall back to IP-based location. Error: ${error.message}`);
                                        window.parent.postMessage({ type: "geolocation", data: `Error: Failed to get location after ${MAX_RETRIES} retries (Code: ${error.code})` }, "*");
                                    }
                                },
                                { enableHighAccuracy: true, timeout: TIMEOUT, maximumAge: 0 }
                            );
                        }
                        checkPermissionsAndGetLocation();
                        </script>
                        <script>
                        window.addEventListener("message", function(event) {
                            if (event.data && event.data.type === "geolocation") {
                                window.parent.postMessage(event.data, "*");
                            }
                        });
                        </script>
                        """
                        st.components.v1.html(location_script, height=0)
                        time.sleep(25)
                        if "geo_data" not in st.session_state or st.session_state["geo_data"] is None:
                            st.text("Wi-Fi triangulation failed after retries. Falling back to IP-based location...")
                            lat, lon = get_fallback_location()
                            if lat is not None and lon is not None:
                                st.session_state["geo_data"] = {"lat": lat, "lon": lon, "accuracy": 2000, "source": "IP-based"}
                            else:
                                st.error("Failed to get any location data. Please use manual input.")
                        if "geo_data" in st.session_state and st.session_state["geo_data"]:
                            geo_data = st.session_state["geo_data"]
                            if isinstance(geo_data, str) and geo_data.startswith("Error:"):
                                st.error(geo_data)
                            elif isinstance(geo_data, dict):
                                lat = float(geo_data.get("lat", 0))
                                lon = float(geo_data.get("lon", 0))
                                if -90 <= lat <= 90 and -180 <= lon <= 180:
                                    success = share_location(
                                        st.session_state.user_id,
                                        lat,
                                        lon,
                                        st.session_state.is_stall_owner and not st.session_state.stall_registered,
                                        st.session_state.stall_name if st.session_state.is_stall_owner else None
                                    )
                                    if success:
                                        st.session_state.last_location = f"({lat}, {lon})"
                                        st.success("Location updated")
                                        if st.session_state.is_stall_owner and not st.session_state.stall_registered:
                                            st.session_state.stall_registered = True
                                            st.rerun()
                                    else:
                                        st.error("Failed to save location to backend.")
                                else:
                                    st.error("Invalid latitude or longitude values.")
                            del st.session_state["geo_data"]

            if st.session_state.user_id and not st.session_state.stall_registered:
                st.session_state.is_stall_owner = st.checkbox("I’m a Stall Owner", key="stall_owner_checkbox")
                if st.session_state.is_stall_owner:
                    st.session_state.stall_name = st.text_input("Stall Name", placeholder="e.g., Tech Stall", key="stall_name_input")
                else:
                    st.session_state.stall_name = None

            use_manual_input = st.checkbox("Use Manual Location Input", key="manual_input_checkbox", disabled=not st.session_state.user_id)
            if use_manual_input and st.session_state.user_id:
                manual_lat = st.text_input("Latitude", value="0", key="manual_lat_input")
                manual_lon = st.text_input("Longitude", value="0", key="manual_lon_input")
                if st.button("Submit Manual Location", key="submit_manual_location"):
                    try:
                        lat = float(manual_lat)
                        lon = float(manual_lon)
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            success = share_location(
                                st.session_state.user_id,
                                lat,
                                lon,
                                st.session_state.is_stall_owner and not st.session_state.stall_registered,
                                st.session_state.stall_name if st.session_state.is_stall_owner else None
                            )
                            if success:
                                st.session_state.last_location = f"({lat}, {lon})"
                                st.success("Location updated")
                                if st.session_state.is_stall_owner and not st.session_state.stall_registered:
                                    st.session_state.stall_registered = True
                                    st.rerun()
                            else:
                                st.error("Failed to save manual location.")
                        else:
                            st.error("Invalid latitude or longitude values.")
                    except ValueError:
                        st.error("Invalid latitude or longitude. Enter numeric values.")

            if st.button("Check Crowd Density", key="crowd_density_button"):
                check_crowd_density()

            if st.session_state.user_id and st.button("Suggest Best Stall", key="suggest_stall_button"):
                suggest_best_stall(st.session_state.user_id)

            st.markdown("""
                <p style="color: orange; font-size: 14px;">
                    Enable location permissions and Wi-Fi for increased accuracy. Ensure Wi-Fi is turned on, even if not connected to a network.
                </p>
            """, unsafe_allow_html=True)

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
            selected_stall = st.selectbox("Select event or stall", df["event"].dropna().unique())
            stall_feedback = df[df["event"] == selected_stall]
            st.write(stall_feedback)
            reply_option = st.radio("Do you want to reply to feedback?", ["No", "Yes"])
            if reply_option == "Yes":
                feedback_options = stall_feedback[stall_feedback["response"].isna() | (stall_feedback["response"] == "")]
                if feedback_options.empty:
                    st.write("No feedback available to reply.")
                    return
                selected_feedback = st.selectbox("Select feedback to reply", feedback_options.index)
                row = df.loc[selected_feedback]
                st.subheader(f"Feedback from {row['name']} ({row['event']})")
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
            
            if st.button("Export User IDs and Interests to CSV"):
                extract_user_id_interests_to_csv()
                st.success("User IDs and interests exported to user_id_interests.csv!")

        elif st.session_state.page == "Chatbot":
            st.markdown("<h2 class='section-title'>Chat with EventBuddy</h2>", unsafe_allow_html=True)
            st.write("Hey there! I’m EventBuddy, your friendly guide from xAI. Ask me about events, stalls, or crowd density—or pick an option below! Examples: 'Register for Tech Fest' or 'How crowded is Tech Stall?'")

            st.markdown('<div class="query-options">', unsafe_allow_html=True)
            query_options = [
                "Register for an Event",
                "Create an Event",
                "Check Crowd Density for a Stall",
                "Get Event Recommendations",
                "Get Stall Feedback"
            ]
            selected_query = st.selectbox("Quick Options", [""] + query_options, key="chat_query")
            if selected_query and st.button("Go", key="go_button"):
                user_input = selected_query
                if "Register" in selected_query and st.session_state.user_id:
                    user_input += ", " + next((e["title"] for e in get_all_events()), "Tech Fest")
                response = get_eventbuddy_response(user_input, st.session_state.user_id, st.session_state.conversation_history)
                st.session_state.conversation_history.append({"role": "user", "message": user_input})
                st.session_state.conversation_history.append({"role": "assistant", "message": response})

            st.markdown('</div>', unsafe_allow_html=True)
            user_input = st.text_input("You:", key="chat_input", placeholder="Type your question here...")
            if user_input and st.session_state.user_id:
                response = get_eventbuddy_response(user_input, st.session_state.user_id, st.session_state.conversation_history)
                st.session_state.conversation_history.append({"role": "user", "message": user_input})
                st.session_state.conversation_history.append({"role": "assistant", "message": response})
            elif user_input and not st.session_state.user_id:
                st.warning("Oops! Please log in with a User ID on the Home page first!")

            st.markdown('<div class="chat-container">', unsafe_allow_html=True)
            for msg in st.session_state.conversation_history:
                message_class = "user-message" if msg["role"] == "user" else "bot-message"
                st.markdown(f'<div class="message-bubble {message_class}">{msg["message"]}</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

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
                unique_key = f"reg_{page}_{event['id']}" if page else f"reg_{event['id']}"
                if st.button("Register", key=unique_key):
                    if register_for_event(user_id, event["id"]):
                        st.success(f"Registered for {event['title']}!")
                    else:
                        st.warning("You’re already registered for this event.")
            if show_delete and user_id and user_id == creator_id:
                unique_key = f"del_{page}_{event['id']}" if page else f"del_{event['id']}"
                if st.button("Delete", key=unique_key):
                    if delete_event(event["id"], user_id):
                        st.success(f"Event '{event['title']}' deleted successfully!")
                        st.rerun()
                    else:
                        st.error("You are not authorized to delete this event.")

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

def get_user_registrations(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT e.* FROM events e JOIN registrations r ON e.id = r.event_id WHERE r.user_id = ?", (user_id,))
    registrations = cursor.fetchall()
    conn.close()
    return registrations

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

def calculate_trend_scores(user_id, decay_rate=0.02):
    conn = get_db_connection()
    cursor = conn.cursor()
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
    
    booking_ids = [booking['id'] for booking in bookings if 'id' in booking and booking['id'] is not None]
    if not booking_ids:
        return {}
    
    min_id = min(booking_ids)
    max_id = max(booking_ids)
    id_range = max_id - min_id if max_id > min_id else 1
    
    for booking in bookings:
        try:
            category = booking['category'] if 'category' in booking else None
            if not category:
                continue
            
            reg_date_str = booking["registration_date"]
            if reg_date_str:
                try:
                    reg_date = datetime.strptime(reg_date_str, "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    if 'id' in booking and booking['id'] is not None:
                        if id_range > 0:
                            days_ago = int((max_id - booking['id']) * 90 / id_range)
                            reg_date = current_date - timedelta(days=days_ago)
                        else:
                            reg_date = current_date - timedelta(days=30)
                    else:
                        reg_date = current_date - timedelta(days=30)
            else:
                if 'id' in booking and booking['id'] is not None:
                    if id_range > 0:
                        days_ago = int((max_id - booking['id']) * 90 / id_range)
                        reg_date = current_date - timedelta(days=days_ago)
                    else:
                        reg_date = current_date - timedelta(days=30)
                else:
                    reg_date = current_date - timedelta(days=30)
            
            days_ago = max((current_date - reg_date).days, 0)
            weight = math.exp(-decay_rate * days_ago)
            category_scores[category] = category_scores.get(category, 0) + weight
        except Exception as e:
            logger.error(f"Error processing booking for user {user_id}: {e}")
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

def generate_event_description(title, category, date=None, venue=None):
    prompt = f"Generate a concise and exciting description for {title} in the {category} category. Highlight the appeal for attendees."
    if date and venue:
        prompt += f" Scheduled on {date} at {venue}."
    else:
        prompt += " in an unspecified location."
    try:
        response = co.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that generates exciting event descriptions."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Groq generation error: {e}")
        return ""

def extract_user_id_interests_to_csv():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, interests FROM users")
    users = cursor.fetchall()
    conn.close()
    
    user_data = [{"id": row["id"], "interests": row["interests"]} for row in users]
    df = pd.DataFrame(user_data)
    df.to_csv("user_id_interests.csv", index=False)
    logger.info("User IDs and interests extracted and saved to user_id_interests.csv")

if __name__ == "__main__":
    main()