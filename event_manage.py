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