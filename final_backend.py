from flask import Flask, request, jsonify
import sqlite3
import csv
import os
from datetime import datetime
from geopy.distance import geodesic
from threading import Lock
from flask_cors import CORS
from collections import defaultdict
import tempfile
import time
import errno

app = Flask(__name__)

# CORS configuration with specific origins
CORS(app, resources={r"/*": {"origins": ["http://localhost:8501", "https://*.ngrok-free.app"], "supports_credentials": True}})

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
    print(f"[{datetime.utcnow().isoformat()}] Initialized SQLite database '{DB_FILE}'")

# Ensure CSV files exist with headers
def initialize_csv():
    with file_lock:
        if not os.path.exists(USER_ID_INTERESTS_FILE):
            with open(USER_ID_INTERESTS_FILE, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["id", "interests"])
            print(f"[{datetime.utcnow().isoformat()}] Initialized {USER_ID_INTERESTS_FILE}")
        
        if not os.path.exists(STALL_PEOPLE_COUNT_FILE):
            with open(STALL_PEOPLE_COUNT_FILE, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["stall_name", "people_count"])
            print(f"[{datetime.utcnow().isoformat()}] Initialized {STALL_PEOPLE_COUNT_FILE}")
        
        if not os.path.exists(STALLS_FILE):
            with open(STALLS_FILE, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["user_id", "stall_name", "latitude", "longitude"])
            print(f"[{datetime.utcnow().isoformat()}] Initialized {STALLS_FILE}")
        
        if not os.path.exists(USER_LOCATIONS_FILE):
            with open(USER_LOCATIONS_FILE, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["user_id", "latitude", "longitude", "timestamp"])
            print(f"[{datetime.utcnow().isoformat()}] Initialized {USER_LOCATIONS_FILE}")
        
        if not os.path.exists(STALL_CATEGORIES_FILE):
            with open(STALL_CATEGORIES_FILE, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["stall_name", "category"])
                writer.writerows([
                    ["Food Stall", "Food"],
                    ["Tech Stall", "Technology"],
                    ["Merchandise Stall", "Products"],
                    ["Game Stall", "Games"]
                ])
            print(f"[{datetime.utcnow().isoformat()}] Initialized {STALL_CATEGORIES_FILE} with default data")
        else:
            print(f"[{datetime.utcnow().isoformat()}] {STALL_CATEGORIES_FILE} already exists")

@app.route("/")
def home():
    return "Flask backend for EventHub crowd monitoring"

# Update stall people count based on user locations
def update_stall_people_count():
    print(f"[{datetime.utcnow().isoformat()}] Recalculating crowd density...")
    stalls = []
    users = []
    
    with file_lock:
        if os.path.exists(STALLS_FILE):
            with open(STALLS_FILE, mode='r') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                stalls = [{'stall_id': row[0], 'stall_name': row[1], 'latitude': float(row[2]), 'longitude': float(row[3])}
                          for row in reader if row and len(row) >= 4]
        
        if os.path.exists(USER_LOCATIONS_FILE):
            with open(USER_LOCATIONS_FILE, mode='r') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                users = [{'user_id': row[0], 'latitude': float(row[1]), 'longitude': float(row[2])}
                         for row in reader if row and len(row) >= 3]
    
    if not stalls:
        print(f"[{datetime.utcnow().isoformat()}] No stalls found, returning default response")
        return {"default": {"crowd_count": 0, "crowd_level": "Very Low", "latitude": 12.8225, "longitude": 80.2250}}
    
    stall_crowd = {}
    for stall in stalls:
        count = sum(1 for user in users if geodesic((stall["latitude"], stall["longitude"]),
                                                    (user["latitude"], user["longitude"])).meters <= 50)
        level = "Very Low" if count <= 1 else "Low" if count <= 3 else "Medium" if count <= 5 else "High" if count <= 7 else "Very High"
        stall_crowd[stall["stall_name"]] = {
            "crowd_count": count,
            "crowd_level": level,
            "latitude": stall["latitude"],
            "longitude": stall["longitude"]
        }
    
    with file_lock:
        with open(STALL_PEOPLE_COUNT_FILE, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["stall_name", "people_count"])
            for stall_name, details in stall_crowd.items():
                writer.writerow([stall_name, details["crowd_count"]])
    
    print(f"[{datetime.utcnow().isoformat()}] Crowd density updated: {stall_crowd}")
    return stall_crowd

# Retrieve user interests from CSV
def get_user_interests_from_csv(user_id):
    if not os.path.exists(USER_ID_INTERESTS_FILE):
        print(f"[{datetime.utcnow().isoformat()}] {USER_ID_INTERESTS_FILE} not found")
        return set()
    
    with file_lock:
        with open(USER_ID_INTERESTS_FILE, mode='r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
            for row in reader:
                if row[0] == str(user_id):
                    interests = row[1].split(",") if row[1] else []
                    print(f"[{datetime.utcnow().isoformat()}] Found interests for user {user_id}: {interests}")
                    return set(interest.strip().lower() for interest in interests)
    print(f"[{datetime.utcnow().isoformat()}] No interests found for user {user_id}")
    return set()

# Retrieve stall categories from CSV
def get_stall_categories():
    categories = {}
    if os.path.exists(STALL_CATEGORIES_FILE):
        with file_lock:
            with open(STALL_CATEGORIES_FILE, mode='r') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                for row in reader:
                    categories[row[0].lower()] = row[1].lower() if row[1] else ""
            print(f"[{datetime.utcnow().isoformat()}] Loaded {len(categories)} stall categories from {STALL_CATEGORIES_FILE}")
    else:
        print(f"[{datetime.utcnow().isoformat()}] Warning: {STALL_CATEGORIES_FILE} not found")
    return categories

# Suggest the best stall based on crowd density and user interests
def suggest_best_stall(user_id):
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
        print(f"[{datetime.utcnow().isoformat()}] No stall data found in {STALL_PEOPLE_COUNT_FILE} for user {user_id}")
        return {"stall": None, "reason": "No stall data available"}
    
    user_interests = get_user_interests_from_csv(user_id)
    if not user_interests:
        print(f"[{datetime.utcnow().isoformat()}] No interests found for user {user_id}")
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
    
    print(f"[{datetime.utcnow().isoformat()}] Suggesting stall for user {user_id}: {best_stall}, reason: {best_reason}")
    return {"stall": best_stall, "reason": best_reason}

@app.route("/save-location", methods=["POST"])
def save_location():
    print(f"[{datetime.utcnow().isoformat()}] Received request at /save-location")
    data = request.json
    print(f"[{datetime.utcnow().isoformat()}] Request data: {data}")
    
    user_id = data.get("user_id")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    is_stall_owner = data.get("is_stall_owner", False)
    stall_name = data.get("stall_name", "")
    
    if not all([user_id, latitude, longitude]):
        print(f"[{datetime.utcnow().isoformat()}] Error: Missing required fields")
        return jsonify({"error": "Missing user_id, latitude, or longitude"}), 400
    
    try:
        latitude = float(latitude)
        longitude = float(longitude)
        if latitude == 1.0 and longitude == 1.0:
            print(f"[{datetime.utcnow().isoformat()}] Error: Invalid default coordinates (1.0, 1.0)")
            return jsonify({"error": "Invalid default coordinates (1.0, 1.0) detected"}), 400
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            print(f"[{datetime.utcnow().isoformat()}] Error: Invalid coordinates")
            return jsonify({"error": "Invalid latitude or longitude values"}), 400
    except (ValueError, TypeError) as e:
        print(f"[{datetime.utcnow().isoformat()}] Error: Coordinates must be numbers - {str(e)}")
        return jsonify({"error": "Latitude and longitude must be numbers"}), 400
    
    with file_lock:
        if is_stall_owner:
            if not stall_name:
                print(f"[{datetime.utcnow().isoformat()}] Error: Stall name required")
                return jsonify({"error": "Stall name required for stall owners"}), 400
            stall_exists = any(row[0] == str(user_id) for row in csv.reader(open(STALLS_FILE, "r")) if row) if os.path.exists(STALLS_FILE) else False
            if not stall_exists:
                with sqlite3.connect(DB_FILE) as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO stalls (user_id, stall_name, latitude, longitude) VALUES (?, ?, ?, ?)",
                                   (user_id, stall_name, latitude, longitude))
                    conn.commit()
                with open(STALLS_FILE, mode='a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow([user_id, stall_name, latitude, longitude])
                print(f"[{datetime.utcnow().isoformat()}] Registered stall for user {user_id}: {stall_name}")
                update_stall_people_count()
                return jsonify({"message": "Stall location stored successfully", "latitude": latitude, "longitude": longitude}), 200
            print(f"[{datetime.utcnow().isoformat()}] Stall already registered for user {user_id}")
            return jsonify({"message": "Stall already registered"}), 200
        else:
            timestamp = datetime.utcnow().isoformat()
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
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
            print(f"[{datetime.utcnow().isoformat()}] Updated location for user {user_id}: {latitude}, {longitude}")
    
    update_stall_people_count()
    return jsonify({"message": "Location updated successfully", "latitude": latitude, "longitude": longitude}), 200

@app.route("/crowd_density", methods=["GET"])
def crowd_density():
    try:
        print(f"[{datetime.utcnow().isoformat()}] Calculating crowd density...")
        stall_crowd = update_stall_people_count()
        return jsonify(stall_crowd), 200
    except Exception as e:
        print(f"[{datetime.utcnow().isoformat()}] Error in crowd_density endpoint: {str(e)}")
        return jsonify({"error": f"Failed to calculate crowd density: {str(e)}"}), 500

@app.route("/suggest_stall", methods=["POST"])
def suggest_stall():
    data = request.json
    user_id = data.get("user_id")
    
    if not user_id:
        print(f"[{datetime.utcnow().isoformat()}] Error: User ID is required")
        return jsonify({"error": "User ID is required"}), 400
    
    suggestion = suggest_best_stall(user_id)
    print(f"[{datetime.utcnow().isoformat()}] Suggestion for user {user_id}: {suggestion}")
    return jsonify(suggestion), 200

if __name__ == "__main__":
    print(f"[{datetime.utcnow().isoformat()}] Starting Flask server...")
    init_db()
    initialize_csv()
    app.run(host='0.0.0.0', port=5000, debug=True)