import streamlit as st
import pandas as pd
import os
import cohere

# File to store feedback data
FEEDBACK_FILE = "feedback.csv"

# Cohere API for AI recommendations
COHERE_API_KEY = "RF13gvo9zsvPvfJYXz8cXEIylIiGWwkeyJQkxL34"
co = cohere.Client(COHERE_API_KEY)

def load_feedback():
    if os.path.exists(FEEDBACK_FILE):
        return pd.read_csv(FEEDBACK_FILE)
    return pd.DataFrame(columns=["name", "feedback", "stall", "rating", "response"])

def recommend_stalls():
    st.title("Stall Recommendations")
    df = load_feedback()
    
    if df.empty:
        st.write("No feedback available to generate recommendations.")
        return
    
    user_interest = st.selectbox("Select a stall you are interested in", df["stall"].dropna().unique())
    
    feedback_text = " ".join(df[df["stall"] == user_interest]["feedback"].dropna().tolist())
    try:
        response = co.generate(
            model="command",
            prompt=f"Based on past feedback and event performance, suggest the best stalls for a user interested in {user_interest}. Feedback data: {feedback_text}"
        )
        recommendation = response.generations[0].text
    except Exception as e:
        recommendation = f"Error fetching recommendation: {str(e)}"
    
    st.subheader("Recommended Stalls")
    st.write(recommendation)

# Page navigation
if __name__ == "__main__":
    recommend_stalls()
