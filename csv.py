def initialize_csv():
    try:
        if not os.path.exists(FEEDBACK_FILE):
            pd.DataFrame(columns=["name", "feedback", "event", "rating", "response"]).to_csv(FEEDBACK_FILE, index=False)
            logger.info("Initialized feedback CSV file.")
        if not os.path.exists("user_interests.csv"):
            pd.DataFrame(columns=["id", "name", "email", "interests"]).to_csv("user_interests.csv", index=False)
            logger.info("Initialized user interests CSV file.")
        if not os.path.exists("user_id_interests.csv"):
            pd.DataFrame(columns=["id", "interests"]).to_csv("user_id_interests.csv", index=False)
            logger.info("Initialized user ID and interests CSV file.")
        if not os.path.exists("stall_people_count.csv"):
            pd.DataFrame(columns=["stall_name", "people_count"]).to_csv("stall_people_count.csv", index=False)
            logger.info("Initialized stall people count CSV file.")
        if not os.path.exists(STALLS_FILE):
            pd.DataFrame(columns=["user_id", "stall_name", "latitude", "longitude"]).to_csv(STALLS_FILE, index=False)
            logger.info("Initialized stalls CSV file.")
        if not os.path.exists(USER_LOCATIONS_FILE):
            pd.DataFrame(columns=["user_id", "latitude", "longitude", "timestamp"]).to_csv(USER_LOCATIONS_FILE, index=False)
            logger.info("Initialized user_locations CSV file.")
    except Exception as e:
        logger.error(f"Error initializing CSV files: {str(e)}")
        st.error(f"CSV initialization failed: {str(e)}")