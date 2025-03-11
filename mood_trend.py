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