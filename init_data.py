import sqlite3
from datetime import datetime  # Add this line

def get_db_connection():
    conn = sqlite3.connect('emr.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db_with_data():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create tables if they don't exist
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

    # Insert sample data
    # Users
    cursor.execute("INSERT INTO users (name, email, interests) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                   ("John Doe", "john@example.com", "Technology,Food"))
    cursor.execute("INSERT INTO users (name, email, interests) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                   ("Jane Smith", "jane@example.com", "Music,Sports"))
    conn.commit()

    # Get user IDs
    cursor.execute("SELECT id FROM users WHERE name = 'John Doe'")
    john_id = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM users WHERE name = 'Jane Smith'")
    jane_id = cursor.fetchone()[0]

    # Events
    cursor.execute("INSERT INTO events (title, date, venue, description, category, created_by) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                   ("Tech Fest", "2025-03-10", "City Hall", "A tech extravaganza!", "Technology", john_id))
    cursor.execute("INSERT INTO events (title, date, venue, description, category, created_by) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                   ("Music Night", "2025-03-15", "Park Amphitheater", "Live music under the stars!", "Music", jane_id))
    conn.commit()

    # Stalls
    cursor.execute("INSERT INTO stalls (user_id, stall_name, latitude, longitude) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                   (john_id, "Tech Stall", 12.8225, 80.2250))
    cursor.execute("INSERT INTO stalls (user_id, stall_name, latitude, longitude) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                   (jane_id, "Food Stall", 12.8230, 80.2260))
    conn.commit()

    # Stall Categories
    cursor.execute("INSERT INTO stall_categories (stall_name, category) VALUES (?, ?) ON CONFLICT DO NOTHING",
                   ("Tech Stall", "Technology"))
    cursor.execute("INSERT INTO stall_categories (stall_name, category) VALUES (?, ?) ON CONFLICT DO NOTHING",
                   ("Food Stall", "Food"))
    conn.commit()

    # User Locations (sample)
    cursor.execute("INSERT INTO user_locations (user_id, latitude, longitude, timestamp) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                   (john_id, 12.8226, 80.2251, datetime.utcnow().isoformat()))
    cursor.execute("INSERT INTO user_locations (user_id, latitude, longitude, timestamp) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                   (jane_id, 12.8231, 80.2261, datetime.utcnow().isoformat()))
    conn.commit()

    conn.close()
    print("Database initialized with sample data successfully.")

if __name__ == "__main__":
    init_db_with_data()