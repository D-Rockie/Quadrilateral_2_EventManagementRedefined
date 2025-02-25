import streamlit as st
import sqlite3
from datetime import datetime
import math

# Database connection
def get_db_connection():
    conn = sqlite3.connect('events.db')  # Replace with your SQLite DB file path
    conn.row_factory = sqlite3.Row  # Allows accessing columns by name
    return conn

# Step 1: Calculate trend scores with exponential decay
def calculate_trend_scores(bookings, decay_rate=0.02):
    category_scores = {}
    current_date = datetime.now()
    for booking in bookings:
        booking_date = datetime.strptime(booking["booking_date"], "%Y-%m-%d")
        days_ago = (current_date - booking_date).days
        weight = math.exp(-decay_rate * days_ago)  # Recent bookings have higher weight
        category = booking["category"]
        category_scores[category] = category_scores.get(category, 0) + weight
    return category_scores

# Step 2: Get top category
def get_top_category(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT category, booking_date FROM bookings WHERE user_id = ?", (user_id,))
    bookings = cursor.fetchall()
    conn.close()
    
    if not bookings:
        return None
    scores = calculate_trend_scores(bookings)
    return max(scores, key=scores.get) if scores else None

# Step 3: Fetch and recommend upcoming events
def recommend_events(user_id):
    top_category = get_top_category(user_id)
    if not top_category:
        return []
    
    conn = get_db_connection()
    cursor = conn.cursor()
    current_date_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT event_id, event_name, category, event_date 
        FROM events 
        WHERE category = ? AND event_date > ? 
        ORDER BY event_date ASC 
        LIMIT 3
    """, (top_category, current_date_str))
    recommendations = cursor.fetchall()
    conn.close()
    return recommendations

# Streamlit UI
def main():
    st.title("Event Recommendations")
    
    # Get list of users for dropdown
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT user_id FROM bookings")
    users = [row["user_id"] for row in cursor.fetchall()]
    conn.close()
    
    # User selection
    user_id = st.selectbox("Select User ID", users)
    
    if user_id:
        # Get recommendations
        recommendations = recommend_events(user_id)
        
        if recommendations:
            st.subheader(f"Recommended Events for {user_id}")
            for event in recommendations:
                st.write(f"**{event['event_name']}** ({event['category']}) - {event['event_date']}")
        else:
            st.write("No upcoming events match your preferences or no booking history found.")

# Setup SQLite database (for demo purposes; run this once separately)
def setup_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            user_id TEXT,
            event_id TEXT,
            category TEXT,
            booking_date TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            event_name TEXT,
            category TEXT,
            event_date TEXT
        )
    ''')
    
    # Insert sample data
    cursor.executescript('''
        DELETE FROM bookings;
        DELETE FROM events;
        INSERT INTO bookings (user_id, event_id, category, booking_date) VALUES
            ('user123', 'e1', 'Music', '2024-12-01'),
            ('user123', 'e2', 'Sports', '2025-01-15'),
            ('user123', 'e3', 'Music', '2025-02-20');
        INSERT INTO events (event_id, event_name, category, event_date) VALUES
            ('e4', 'Spring Concert', 'Music', '2025-03-01'),
            ('e5', 'Football Match', 'Sports', '2025-03-10'),
            ('e6', 'Jazz Night', 'Music', '2025-04-01');
    ''')
    conn.commit()
    conn.close()

if __name__ == "__main__":
    # Uncomment the line below to initialize the database (run once)
    # setup_database()
    main()