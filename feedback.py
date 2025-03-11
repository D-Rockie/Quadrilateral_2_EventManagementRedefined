def load_feedback():
    if os.path.exists(FEEDBACK_FILE):
        return pd.read_csv(FEEDBACK_FILE)
    return pd.DataFrame(columns=["name", "feedback", "event", "rating", "response"])

def save_feedback(df):
    df.to_csv(FEEDBACK_FILE, index=False)