from flask import Flask, request, jsonify
import sqlite3
import csv
import os
from datetime import datetime
from geopy.distance import geodesic
from threading import Lock
from flask_cors import CORS
from collections import defaultdict

app = Flask(__name__)
CORS(app)

# SQLite database file
DB_FILE = 'emr.db'

# CSV file paths
USER_ID_INTERESTS_FILE = "user_id_interests.csv"
STALL_PEOPLE_COUNT_FILE = "stall_people_count.csv"
STALLS_FILE = "stalls.csv"
USER_LOCATIONS_FILE = "user_locations.csv"
STALL_CATEGORIES_FILE = "stall_categories.csv"

# Thread lock for database and file operations
file_lock = Lock()

# Initialize SQLite database with necessary tables
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
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
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            interests TEXT
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS stall_categories (
            stall_name TEXT PRIMARY KEY,
            category TEXT
        )''')
        conn.commit()

# Ensure CSV files exist with headers
def initialize_csv():
    with file_lock:
        if not os.path.exists(USER_ID_INTERESTS_FILE):
            with open(USER_ID_INTERESTS_FILE, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["id", "interests"])
            print("Initialized user_id_interests.csv file.")
        
        if not os.path.exists(STALL_PEOPLE_COUNT_FILE):
            with open(STALL_PEOPLE_COUNT_FILE, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["stall_name", "people_count"])
            print("Initialized stall_people_count.csv file.")
        
        if not os.path.exists(STALLS_FILE):
            with open(STALLS_FILE, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["user_id", "stall_name", "latitude", "longitude"])
            print("Initialized stalls.csv file.")
        
        if not os.path.exists(USER_LOCATIONS_FILE):
            with open(USER_LOCATIONS_FILE, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["user_id", "latitude", "longitude", "timestamp"])
            print("Initialized user_locations.csv file.")
        
        # stall_categories.csv is assumed to be pre-populated, so no initialization here
        if not os.path.exists(STALL_CATEGORIES_FILE):
            print("Warning: stall_categories.csv not found. Stall suggestions may lack category data.")

@app.route("/")
def home():
    return "Flask backend for EventHub crowd monitoring"

def update_stall_people_count():
    """Update stall_people_count.csv with current people count using SQLite data, mirrored in CSV."""
    stalls = []
    users = []
    
    with file_lock:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, stall_name, latitude, longitude FROM stalls")
            stalls = [{'stall_id': row[0], 'stall_name': row[1], 'latitude': row[2], 'longitude': row[3]} for row in cursor.fetchall()]
            
            cursor.execute("SELECT user_id, latitude, longitude FROM user_locations")
            users = [{'user_id': row[0], 'latitude': row[1], 'longitude': row[2]} for row in cursor.fetchall()]
    
    if not stalls:
        print("No stalls found in SQLite. Returning default response.")
        return {
            "default": {
                "crowd_count": 0,
                "crowd_level": "Very Low",
                "latitude": 37.7749,
                "longitude": -122.4194
            }
        }
    
    stall_crowd = {}
    for stall in stalls:
        count = 0
        stall_location = (stall["latitude"], stall["longitude"])
        
        if users:
            for user in users:
                user_location = (user["latitude"], user["longitude"])
                distance = geodesic(stall_location, user_location).meters
                if distance <= 50:
                    count += 1
        
        if count <= 1:
            level = "Very Low"
        elif count <= 3:
            level = "Low"
        elif count <= 5:
            level = "Medium"
        elif count <= 7:
            level = "High"
        else:
            level = "Very High"
        
        stall_crowd[stall["stall_name"]] = {
            "crowd_count": count,
            "crowd_level": level,
            "latitude": stall["latitude"],
            "longitude": stall["longitude"]
        }
    
    # Update stall_people_count.csv
    with file_lock:
        with open(STALL_PEOPLE_COUNT_FILE, "w", newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["stall_name", "people_count"])
            for stall_name, details in stall_crowd.items():
                if stall_name != "default":
                    writer.writerow([stall_name, details["crowd_count"]])
    
    print(f"Crowd density calculated from SQLite and updated in CSV: {stall_crowd}")
    return stall_crowd

def get_user_interests_from_csv(user_id):
    """Retrieve user interests from user_id_interests.csv."""
    if not os.path.exists(USER_ID_INTERESTS_FILE):
        return set()
    
    with file_lock:
        with open(USER_ID_INTERESTS_FILE, mode='r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
            for row in reader:
                if row[0] == str(user_id):
                    interests = row[1].split(",") if row[1] else []
                    return set(interest.strip().lower() for interest in interests)
    return set()

def get_stall_categories():
    """Retrieve stall categories from stall_categories.csv (fallback to SQLite if CSV missing)."""
    categories = {}
    if os.path.exists(STALL_CATEGORIES_FILE):
        with file_lock:
            with open(STALL_CATEGORIES_FILE, mode='r') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                for row in reader:
                    categories[row[0].lower()] = row[1].lower() if row[1] else ""
    else:
        with file_lock:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT stall_name, category FROM stall_categories")
                for row in cursor.fetchall():
                    categories[row[0].lower()] = row[1].lower() if row[1] else ""
    return categories

def suggest_best_stall(user_id):
    """Suggest the best stall based on crowd density from stall_people_count.csv and user interests from user_id_interests.csv."""
    stall_counts = {}
    if os.path.exists(STALL_PEOPLE_COUNT_FILE):
        with file_lock:
            with open(STALL_PEOPLE_COUNT_FILE, mode='r') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                for row in reader:
                    if len(row) >= 2:
                        stall_counts[row[0]] = int(row[1] if row[1] else 0)
    
    if not stall_counts:
        print(f"No stall data found in {STALL_PEOPLE_COUNT_FILE} for user {user_id}")
        return {"stall": None, "reason": "No stall data available"}
    
    user_interests = get_user_interests_from_csv(user_id)
    if not user_interests:
        print(f"No interests found for user {user_id} in {USER_ID_INTERESTS_FILE}")
        return {"stall": None, "reason": "No user interests available"}

    stall_categories = get_stall_categories()
    
    best_stall = None
    best_reason = "No suitable stall found"
    min_crowd = float('inf')
    best_interest_match = None
    
    for stall_name, crowd_count in stall_counts.items():
        interest_score = 0
        
        if stall_name.lower() in stall_categories:
            stall_cat = stall_categories[stall_name.lower()]
            if stall_cat in user_interests:
                interest_score = 2
            elif any(cat in stall_cat for cat in user_interests):
                interest_score = 1
        
        if crowd_count < min_crowd or (crowd_count == min_crowd and interest_score > (best_interest_match or 0)):
            min_crowd = crowd_count
            best_stall = stall_name
            best_interest_match = interest_score
            if interest_score > 0:
                best_reason = f"Recommended due to low crowd ({crowd_count} people) and matching {stall_cat} interest"
            else:
                best_reason = f"Recommended due to low crowd ({crowd_count} people)"
    
    print(f"Suggesting stall for user {user_id} from CSV: {best_stall}, reason: {best_reason}")
    return {"stall": best_stall, "reason": best_reason}

@app.route("/save-location", methods=["POST"])
def save_location():
    print("Received request at /save-location")
    data = request.json
    print("Request data:", data)
    
    user_id = data.get("user_id")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    is_stall_owner = data.get("is_stall_owner", False)
    stall_name = data.get("stall_name", "")
    
    if not all([user_id, latitude, longitude]):
        print("Error: Missing data")
        return jsonify({"error": "Missing user_id, latitude, or longitude"}), 400
    
    try:
        latitude = float(latitude)
        longitude = float(longitude)
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            print("Error: Invalid coordinates")
            return jsonify({"error": "Invalid latitude or longitude values"}), 400
    except (ValueError, TypeError) as e:
        print(f"Error: Coordinates must be numbers - {str(e)}")
        return jsonify({"error": "Latitude and longitude must be numbers"}), 400
    
    with file_lock:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            if is_stall_owner:
                if not stall_name:
                    print("Error: Stall owner must provide a stall name")
                    return jsonify({"error": "Stall name required for stall owners"}), 400
                
                cursor.execute("SELECT user_id FROM stalls WHERE user_id = ?", (user_id,))
                if not cursor.fetchone():
                    print(f"Registering stall in SQLite - User ID: {user_id}, Stall Name: {stall_name}, Latitude: {latitude}, Longitude: {longitude}")
                    cursor.execute("INSERT INTO stalls (user_id, stall_name, latitude, longitude) VALUES (?, ?, ?, ?)",
                                   (user_id, stall_name, latitude, longitude))
                    conn.commit()
                    with open(STALLS_FILE, mode='a', newline='') as file:
                        writer = csv.writer(file)
                        writer.writerow([user_id, stall_name, latitude, longitude])
                    print("Stall location stored in SQLite and stalls.csv.")
                    return jsonify({"message": "Stall location stored successfully"}), 200
                else:
                    print("Stall already registered for this user in SQLite.")
                    return jsonify({"message": "Stall already registered"}), 200
            else:
                timestamp = datetime.utcnow().isoformat()
                cursor.execute("REPLACE INTO user_locations (user_id, latitude, longitude, timestamp) VALUES (?, ?, ?, ?)",
                               (user_id, latitude, longitude, timestamp))
                conn.commit()
                all_rows = []
                user_exists = False
                if os.path.exists(USER_LOCATIONS_FILE):
                    with open(USER_LOCATIONS_FILE, "r") as file:
                        reader = csv.reader(file)
                        header = next(reader)
                        all_rows.append(header)
                        for row in reader:
                            if row and row[0] == str(user_id):
                                all_rows.append([user_id, latitude, longitude, timestamp])
                                user_exists = True
                            else:
                                all_rows.append(row)
                if not user_exists:
                    all_rows.append([user_id, latitude, longitude, timestamp])
                with open(USER_LOCATIONS_FILE, "w", newline='') as file:
                    writer = csv.writer(file)
                    writer.writerows(all_rows)
                print(f"Updated user location - User ID: {user_id}, Latitude: {latitude}, Longitude: {longitude}, Timestamp: {timestamp}")
    
    update_stall_people_count()
    print("Location processed successfully.")
    return jsonify({"message": "Location updated successfully"}), 200

@app.route("/crowd_density", methods=["GET"])
def crowd_density():
    print("Calculating crowd density from SQLite...")
    stall_crowd = update_stall_people_count()
    
    if not stall_crowd:
        print("No stalls or users found in SQLite. Returning default response.")
        return jsonify({
            "default": {
                "crowd_count": 0,
                "crowd_level": "Very Low",
                "latitude": 37.7749,
                "longitude": -122.4194
            }
        }), 200
    
    print(f"Crowd density calculated successfully from SQLite: {stall_crowd}")
    return jsonify(stall_crowd)

@app.route("/suggest_stall", methods=["POST"])
def suggest_stall():
    data = request.json
    user_id = data.get("user_id")
    
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    
    suggestion = suggest_best_stall(user_id)
    print(f"Suggestion for user {user_id} from CSV: {suggestion}")
    return jsonify(suggestion)

if __name__ == "__main__":
    print("Starting Flask server...")
    init_db()
    initialize_csv()
    app.run(host='0.0.0.0', port=5000, debug=True)
