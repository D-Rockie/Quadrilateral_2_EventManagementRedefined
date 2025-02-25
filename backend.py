from flask import Flask, request, jsonify
import csv
import os
import pandas as pd
from datetime import datetime
from geopy.distance import geodesic
from threading import Lock
from flask_cors import CORS
from collections import defaultdict

app = Flask(__name__)

# Enable CORS for all origins (or specify frontend origin for security)
CORS(app)

# File paths
USER_LOCATIONS_FILE = "user_locations.csv"
STALLS_FILE = "stalls.csv"
STALL_PEOPLE_COUNT_FILE = "stall_people_count.csv"
USER_INTERESTS_FILE = "user_interests.csv"
STALL_CATEGORIES_FILE = "stall_categories.csv"

# Thread lock for file writing
file_lock = Lock()

# Delete old CSV files if they exist (exclude user_interests.csv and stall_categories.csv)
for file in [USER_LOCATIONS_FILE, STALLS_FILE, STALL_PEOPLE_COUNT_FILE]:
    if os.path.exists(file):
        os.remove(file)
        print(f"Deleted old file: {file}")
    else:
        print(f"No existing file found: {file}")

# Ensure CSV files exist with headers (exclude user_interests.csv and stall_categories.csv)
def initialize_csv():
    with file_lock:
        if not os.path.exists(USER_LOCATIONS_FILE):
            with open(USER_LOCATIONS_FILE, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["user_id", "latitude", "longitude", "timestamp"])
            print("Initialized user locations CSV file.")
        
        if not os.path.exists(STALLS_FILE):
            with open(STALLS_FILE, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["user_id", "stall_name", "latitude", "longitude"])
            print("Initialized stalls CSV file.")
        
        if not os.path.exists(STALL_PEOPLE_COUNT_FILE):
            with open(STALL_PEOPLE_COUNT_FILE, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["stall_name", "people_count"])
            print("Initialized stall people count CSV file.")

@app.route("/")
def home():
    return "Flask backend for EventHub crowd monitoring"

def update_stall_people_count():
    """Update stall_people_count.csv with the current people count per stall using crowd_density logic."""
    stalls = []
    users = []
    
    with file_lock:
        if os.path.exists(STALLS_FILE):
            with open(STALLS_FILE, mode='r') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                for row in reader:
                    stalls.append({"stall_name": row[1], "latitude": float(row[2]), "longitude": float(row[3])})
        
        if os.path.exists(USER_LOCATIONS_FILE):
            with open(USER_LOCATIONS_FILE, mode='r') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                for row in reader:
                    users.append({"latitude": float(row[1]), "longitude": float(row[2])})
    
    stall_counts = {}
    
    for stall in stalls:
        count = 0
        stall_location = (stall["latitude"], stall["longitude"])
        
        for user in users:
            user_location = (user["latitude"], user["longitude"])
            distance = geodesic(stall_location, user_location).meters
            if distance <= 50:  # Minimum distance for crowd counting
                count += 1
        
        stall_counts[stall["stall_name"]] = count
    
    # Update or create stall_people_count.csv with the latest counts
    with file_lock:
        all_counts = []
        for stall_name, count in stall_counts.items():
            all_counts.append([stall_name, count])
        
        with open(STALL_PEOPLE_COUNT_FILE, "w", newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["stall_name", "people_count"])
            writer.writerows(all_counts)
    
    print("Stall people count updated successfully.")

def get_user_interests(user_id):
    """Retrieve user interests from user_interests.csv."""
    if not os.path.exists(USER_INTERESTS_FILE):
        return set()
    
    with file_lock:
        with open(USER_INTERESTS_FILE, mode='r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
            for row in reader:
                if row[0] == user_id:
                    interests = row[3].split(",") if row[3] else []
                    return set(interest.strip().lower() for interest in interests)
    return set()

def get_stall_categories():
    """Retrieve stall categories from stall_categories.csv."""
    categories = {}
    if not os.path.exists(STALL_CATEGORIES_FILE):
        return categories
    
    with file_lock:
        with open(STALL_CATEGORIES_FILE, mode='r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
            for row in reader:
                categories[row[0].lower()] = row[1].lower() if row[1] else ""
    return categories

def suggest_best_stall(user_id):
    """Suggest the best stall based on crowd density and general user interests (no prioritization)."""
    # Get current stall people counts
    stall_counts = {}
    if os.path.exists(STALL_PEOPLE_COUNT_FILE):
        with file_lock:
            with open(STALL_PEOPLE_COUNT_FILE, mode='r') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                for row in reader:
                    stall_counts[row[0]] = int(row[1])
    
    # Get user interests
    user_interests = get_user_interests(user_id)
    if not user_interests:
        print(f"No interests found for user {user_id}")
        return {"stall": None, "reason": "No user interests available"}

    # Get stall categories
    stall_categories = get_stall_categories()
    
    # Calculate scores for each stall (generalized, no prioritization)
    best_stall = None
    best_reason = "No suitable stall found"
    
    # Track stalls with the lowest crowd and best interest match
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
    
    print(f"Suggesting stall for user {user_id}: {best_stall}, reason: {best_reason}")
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
    
    # Debug: Log the raw values to identify the issue
    print(f"Raw latitude: {latitude}, type: {type(latitude)}")
    print(f"Raw longitude: {longitude}, type: {type(longitude)}")
    
    try:
        # Attempt to convert strings to floats if they are numbers
        if isinstance(latitude, str):
            latitude = float(latitude.strip())
        if isinstance(longitude, str):
            longitude = float(longitude.strip())
        
        # Validate the converted numbers
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            print("Error: Invalid coordinates")
            return jsonify({"error": "Invalid latitude or longitude values"}), 400
    except (ValueError, TypeError) as e:
        print(f"Error: Coordinates must be numbers - {str(e)}")
        return jsonify({"error": "Latitude and longitude must be numbers"}), 400
    
    # Handle stall owner registration
    if is_stall_owner:
        if not stall_name:
            print("Error: Stall owner must provide a stall name")
            return jsonify({"error": "Stall name required for stall owners"}), 400
        
        stall_exists = False
        with file_lock:
            if os.path.exists(STALLS_FILE):
                with open(STALLS_FILE, "r") as file:
                    reader = csv.reader(file)
                    next(reader, None)  # Skip header if it exists, handle empty file
                    for row in reader:
                        if row and row[0] == user_id:
                            stall_exists = True
                            break
        
        if not stall_exists:
            print(f"Registering stall - User ID: {user_id}, Stall Name: {stall_name}, Latitude: {latitude}, Longitude: {longitude}")
            with file_lock:
                with open(STALLS_FILE, mode='a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow([user_id, stall_name, latitude, longitude])
            print("Stall location stored successfully.")
            return jsonify({"message": "Stall location stored successfully"}), 200
        else:
            print("Stall already registered for this user.")
            return jsonify({"message": "Stall already registered"}), 200
    
    # Handle user location update (append new rows for new user_ids, update existing ones)
    timestamp = datetime.utcnow().isoformat()
    user_exists = False
    all_rows = []
    
    with file_lock:
        if os.path.exists(USER_LOCATIONS_FILE):
            with open(USER_LOCATIONS_FILE, "r") as file:
                reader = csv.reader(file)
                header = next(reader)  # Preserve header
                all_rows.append(header)  # Add header to all_rows
                for row in reader:
                    if row and row[0] == user_id:
                        all_rows.append([user_id, latitude, longitude, timestamp])
                        user_exists = True
                    else:
                        all_rows.append(row)
        
        # If user doesn't exist, append a new row; otherwise, the updated row is already in all_rows
        if not user_exists:
            all_rows.append([user_id, latitude, longitude, timestamp])
            print(f"Stored new user location - User ID: {user_id}, Latitude: {latitude}, Longitude: {longitude}, Timestamp: {timestamp}")
        else:
            print(f"Updated user location - User ID: {user_id}, Latitude: {latitude}, Longitude: {longitude}, Timestamp: {timestamp}")
        
        # Write all rows back to the file
        with open(USER_LOCATIONS_FILE, "w", newline='') as file:
            writer = csv.writer(file)
            writer.writerows(all_rows)
    
    # Update stall people count after each location update
    update_stall_people_count()
    
    print("Location processed successfully.")
    return jsonify({"message": "Location updated successfully"}), 200

@app.route("/crowd_density", methods=["GET"])
def crowd_density():
    print("Calculating crowd density...")
    stalls = []
    users = []
    
    with file_lock:
        if os.path.exists(STALLS_FILE):
            with open(STALLS_FILE, mode='r') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                for row in reader:
                    stalls.append({"stall_id": row[0], "stall_name": row[1], "latitude": float(row[2]), "longitude": float(row[3])})
        
        if os.path.exists(USER_LOCATIONS_FILE):
            with open(USER_LOCATIONS_FILE, mode='r') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                for row in reader:
                    users.append({"user_id": row[0], "latitude": float(row[1]), "longitude": float(row[2])})
    
    if not stalls:
        print("No stalls found in the database.")
        return jsonify({"error": "No stalls registered."}), 400
    
    if not users:
        print("No user locations found in the database.")
        return jsonify({"error": "No users available for crowd calculation."}), 400
    
    stall_crowd = {}
    
    for stall in stalls:
        count = 0
        stall_location = (stall["latitude"], stall["longitude"])
        
        for user in users:
            user_location = (user["latitude"], user["longitude"])
            distance = geodesic(stall_location, user_location).meters
            if distance <= 50:  # Minimum distance for crowd counting
                count += 1
        
        # Classify crowd density level
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
        
        stall_crowd[stall["stall_name"]] = {"crowd_count": count, "crowd_level": level}
    
    print(f"Crowd density calculated successfully: {stall_crowd}")
    return jsonify(stall_crowd)

@app.route("/suggest_stall", methods=["POST"])
def suggest_stall():
    data = request.json
    user_id = data.get("user_id")
    
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    
    suggestion = suggest_best_stall(user_id)
    print(f"Suggestion for user {user_id}: {suggestion}")
    return jsonify(suggestion)

if __name__ == "__main__":
    print("Starting Flask server...")
    initialize_csv()
    app.run(host='0.0.0.0', port=5000, debug=True)