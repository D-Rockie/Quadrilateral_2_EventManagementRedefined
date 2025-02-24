import sqlite3
import streamlit as st
from textblob import TextBlob
import cohere
import logging
import os

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
    "positive": ["Sports", "Music", "Games"],  # Upbeat, energetic events
    "negative": ["Art"],                       # Calming, reflective events
    "neutral": CATEGORIES                      # All categories for neutral mood
}

# --- Database Setup ---
def get_db_connection():
    conn = sqlite3.connect('emr.db')
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Users table
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        interests TEXT
    )''')
    # Check if events table exists and add created_by column if missing
    cursor.execute('''SELECT count(*) FROM sqlite_master WHERE type='table' AND name='events' ''')
    if cursor.fetchone()[0] == 1:  # Table exists
        # Check if created_by column exists
        cursor.execute('''PRAGMA table_info(events)''')
        columns = {row[1] for row in cursor.fetchall()}  # Get column names
        if 'created_by' not in columns:
            cursor.execute('''ALTER TABLE events ADD COLUMN created_by INTEGER''')
            logger.info("Added 'created_by' column to events table.")
            # SQLite doesn't allow adding FOREIGN KEY via ALTER TABLE directly; we need to handle this carefully
            # Instead, we'll ensure the foreign key is set when creating the table or leave it as is for now
    else:  # Table doesn't exist, create it with the foreign key
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
    # Registrations table
    cursor.execute('''CREATE TABLE IF NOT EXISTS registrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        event_id INTEGER,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (event_id) REFERENCES events(id)
    )''')
    conn.commit()
    conn.close()

# --- Cohere Description Generation ---
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

# --- Database Helper Functions ---
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
    return event_id

def get_all_events():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events ORDER BY id DESC")  # Order by newest first for featured
    events = cursor.fetchall()
    conn.close()
    return events

def clear_all_events():
    """Clear all events from the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM events")
    cursor.execute("DELETE FROM registrations")  # Clear registrations related to events
    conn.commit()
    conn.close()
    logger.info("All events and registrations cleared from the database.")

def delete_event(event_id, user_id):
    """Delete an event, only if the user is the creator."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT created_by FROM events WHERE id = ?", (event_id,))
    event = cursor.fetchone()
    if not event or event['created_by'] != user_id:
        conn.close()
        return False
    cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
    cursor.execute("DELETE FROM registrations WHERE event_id = ?", (event_id,))  # Clear related registrations
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
    sentiment = blob.sentiment.polarity  # -1 (negative) to 1 (positive)
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

# --- UI Helper Function ---
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

# --- Streamlit App with Banner UI ---
def main():
    # Clear existing events before running (optional, for testing)
    if os.path.exists('emr.db'):
        clear_all_events()

    init_db()  # Initialize database

    # Custom CSS for banner and buttons
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
                width: 140px; /* Fixed width for consistent sizing */
                height: 40px; /* Fixed height for consistent sizing */
            }
            .banner button:hover {
                background-color: #555;
            }
            .stTitle {
                color: white;
                text-align: center;
            }
        </style>
    """, unsafe_allow_html=True)

    # Banner with styled title and buttons
    st.markdown('<div class="banner">', unsafe_allow_html=True)
    st.markdown('<h1 class="stTitle">Event Management Redefined</h1>', unsafe_allow_html=True)
    
    # Horizontal buttons using columns with custom styling
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        if st.button("Home"):
            st.session_state.page = "Home"
    with col2:
        if st.button("Registration"):
            st.session_state.page = "Registration"
    with col3:
        if st.button("All Events"):
            st.session_state.page = "All Events"
    with col4:
        if st.button("My Events"):
            st.session_state.page = "My Events"
    with col5:
        if st.button("Recommendations"):
            st.session_state.page = "Recommendations"
    with col6:
        if st.button("Add Event"):
            st.session_state.page = "Add Event"
    
    st.markdown('</div>', unsafe_allow_html=True)

    # Default page if not set
    if 'page' not in st.session_state:
        st.session_state.page = "Home"

    # Persistent user ID using session state
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None

    # Pages content
    if st.session_state.page == "Home":
        st.header("Welcome to Event Management Redefined!")
        st.write("Redefining event management with AI-powered recommendations and smart tools.")

        # Login (for existing users)
        st.subheader("Log In")
        user_id = st.number_input("Enter your User ID", min_value=1, step=1)
        if st.button("Log In"):
            user = get_user(user_id)
            if user:
                st.session_state.user_id = user_id
                st.success(f"Logged in as {user['name']}!")
            else:
                st.error("Invalid User ID. Please register first.")

        # Link to Registration for new users
        if st.button("Not registered yet? Click here to register"):
            st.session_state.page = "Registration"

        # Featured Events (show 3 most recent events)
        st.subheader("Featured Events")
        events = get_all_events()
        if events:
            st.write("Check out our latest and most exciting events!")
            for event in events[:3]:  # Show up to 3 most recent events (ordered by id DESC)
                display_event(event, show_register=True, user_id=st.session_state.user_id, creator_id=event['created_by'])
        else:
            st.write("No featured events available yet.")

    elif st.session_state.page == "Registration":
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
                    st.session_state.page = "Home"  # Redirect back to Home after registration

    elif st.session_state.page == "All Events":
        st.header("All Upcoming Events")
        events = get_all_events()
        if events:
            for event in events:
                display_event(event, show_register=True, show_delete=True, user_id=st.session_state.user_id, creator_id=event['created_by'])
        else:
            st.write("No events available yet.")

    elif st.session_state.page == "My Events":
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

    elif st.session_state.page == "Recommendations":
        st.header("Personalized Recommendations")
        if not st.session_state.user_id:
            st.warning("Please log in first.")
        else:
            # Interest-based recommendations
            st.subheader("Based on Your Interests")
            interest_events = get_interest_based_events(st.session_state.user_id)
            if interest_events:
                for event in interest_events:
                    display_event(event, show_register=True, user_id=st.session_state.user_id, creator_id=event['created_by'])
            else:
                st.write("No interest-based recommendations yet. Update your interests on the Registration page!")

            # Mood-based recommendations
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

    elif st.session_state.page == "Add Event":
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

if __name__ == "__main__":
    main()