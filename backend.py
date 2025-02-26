from flask import Flask, request, jsonify, render_template
import csv
import os
import pandas as pd
from datetime import datetime
from geopy.distance import geodesic
from threading import Lock
from flask_cors import CORS

app = Flask(__name__)

# Enable CORS for all origins (or specify frontend origin for security)
CORS(app)

# File paths
USER_LOCATIONS_FILE = "user_locations.csv"
STALLS_FILE = "stalls.csv"

# Thread lock for file writing
file_lock = Lock()

# Delete old CSV files if they exist
for file in [USER_LOCATIONS_FILE, STALLS_FILE]:
    if os.path.exists(file):
        os.remove(file)
        print(f"Deleted old file: {file}")
    else:
        print(f"No existing file found: {file}")

# Ensure CSV files exist with headers
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

@app.route("/")
def home():
    return render_template("index.html")

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
    except (ValueError, TypeError):
        print("Error: Coordinates must be numbers")
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
    
    print("Crowd density calculated successfully.")
    return jsonify(stall_crowd)

if __name__ == "__main__":
    print("Starting Flask server...")
    initialize_csv()
    app.run(host='0.0.0.0', port=5000, debug=True)
