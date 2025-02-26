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

@app.route("/")
def home():
    return "Flask backend for EventHub crowd monitoring"

def update_stall_people_count():
    """Update stall_people_count.csv with the current people count per stall using SQLite data."""
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
        print("No stalls found in the database. Returning default response.")
        return {
            "default": {
                "crowd_count": 0,
                "crowd_level": "Very Low",
                "latitude": 37.7749,  # Default San Francisco coordinates
                "longitude": -122.4194
            }
        }
    
    if not users:
        print("No user locations found in the database.")
        with file_lock:
            with open(STALL_PEOPLE_COUNT_FILE, "w", newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["stall_name", "people_count"])
                for stall in stalls:
                    writer.writerow([stall["stall_name"], 0])
        return {stall["stall_name"]: {
            "crowd_count": 0,
            "crowd_level": "Very Low",
            "latitude": stall["latitude"],
            "longitude": stall["longitude"]
        } for stall in stalls}
    
    stall_crowd = {}
    for stall in stalls:
        count = 0
        stall_location = (stall["latitude"], stall["longitude"])
        for user in users:
            user_location = (user["latitude"], user["longitude"])
            distance = geodesic(stall_location, user_location).meters
            if distance <= 50:  # Minimum distance for crowd counting
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
                writer.writerow([stall_name, details["crowd_count"]])
    
    print(f"Crowd density calculated successfully from SQLite and updated in CSV: {stall_crowd}")
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
                if row[0] == str(user_id):  # Ensure matching string format
                    interests = row[1].split(",") if row[1] else []
                    return set(interest.strip().lower() for interest in interests)
    return set()

def get_stall_categories():
    """Retrieve stall categories from SQLite (kept for consistency with other features)."""
    categories = {}
    with file_lock:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT stall_name, category FROM stall_categories")
            for row in cursor.fetchall():
                categories[row[0].lower()] = row[1].lower() if row[1] else ""
    return categories

def suggest_best_stall(user_id):
    """Suggest the best stall based on crowd density from CSV and user interests from CSV."""
    # Get current stall people counts from CSV
    stall_counts = {}
    if os.path.exists(STALL_PEOPLE_COUNT_FILE):
        with file_lock:
            with open(STALL_PEOPLE_COUNT_FILE, mode='r') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                for row in reader:
                    stall_counts[row[0]] = int(row[1] if row[1] else 0)
    
    # Get user interests from CSV
    user_interests = get_user_interests_from_csv(user_id)
    if not user_interests:
        print(f"No interests found for user {user_id} in CSV")
        return {"stall": None, "reason": "No user interests available"}

    # Get stall categories (still from SQLite for consistency with other features)
    stall_categories = get_stall_categories()
    
    # Calculate scores for each stall (using CSV data)
    best_stall = None
    best_reason = "No suitable stall found"
    min_crowd = float('inf')
    best_interest_match = None
    
    for stall_name in stall_counts.keys():
        crowd_count = stall_counts[stall_name]
        interest_score = 0
        
        if stall_name.lower() in stall_categories:
            stall_cat = stall_categories[stall_name.lower()]
            if stall_cat in user_interests:
                interest_score = 2  # High score for exact category match
            elif any(cat in stall_cat for cat in user_interests):
                interest_score = 1  # Moderate score for partial match
        
        # If crowds are equal, prioritize by interest match (higher interest_score wins)
        if crowd_count < min_crowd or (crowd_count == min_crowd and interest_score > (best_interest_match or 0)):
            min_crowd = crowd_count
            best_stall = stall_name
            best_interest_match = interest_score
            if interest_score > 0:
                best_reason = f"Recommended due to low crowd and matching {stall_cat} interest"
            else:
                best_reason = "Recommended due to low crowd"
    
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
                    print(f"Registering stall - User ID: {user_id}, Stall Name: {stall_name}, Latitude: {latitude}, Longitude: {longitude}")
                    cursor.execute("INSERT INTO stalls (user_id, stall_name, latitude, longitude) VALUES (?, ?, ?, ?)",
                                   (user_id, stall_name, latitude, longitude))
                    conn.commit()
                    print("Stall location stored successfully in SQLite.")
                    return jsonify({"message": "Stall location stored successfully"}), 200
                else:
                    print("Stall already registered for this user.")
                    return jsonify({"message": "Stall already registered"}), 200
            else:
                timestamp = datetime.utcnow().isoformat()
                cursor.execute("REPLACE INTO user_locations (user_id, latitude, longitude, timestamp) VALUES (?, ?, ?, ?)",
                               (user_id, latitude, longitude, timestamp))
                conn.commit()
                print(f"Updated user location - User ID: {user_id}, Latitude: {latitude}, Longitude: {longitude}, Timestamp: {timestamp}")
    
    update_stall_people_count()
    print("Location processed successfully.")
    return jsonify({"message": "Location updated successfully"}), 200

@app.route("/crowd_density", methods=["GET"])
def crowd_density():
    print("Calculating crowd density from SQLite...")
    stall_crowd = update_stall_people_count()
    
    if not stall_crowd:
        print("No stalls or users found in the database. Returning default response.")
        return jsonify({
            "default": {
                "crowd_count": 0,
                "crowd_level": "Very Low",
                "latitude": 37.7749,  # Default San Francisco coordinates
                "longitude": -122.4194
            }
        }), 200  # Return 200 instead of 400 for a default response
    
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
