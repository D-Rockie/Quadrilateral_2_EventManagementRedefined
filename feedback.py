import streamlit as st
import pandas as pd
import os
import requests
import cohere
import matplotlib.pyplot as plt

# File to store feedback data
FEEDBACK_FILE = "feedback.csv"

# Cohere API for event performance prediction
COHERE_API_KEY = "RF13gvo9zsvPvfJYXz8cXEIylIiGWwkeyJQkxL34"
co = cohere.Client(COHERE_API_KEY)

def load_feedback():
    if os.path.exists(FEEDBACK_FILE):
        return pd.read_csv(FEEDBACK_FILE)
    return pd.DataFrame(columns=["name", "feedback", "event", "rating", "response"])

def save_feedback(df):
    df.to_csv(FEEDBACK_FILE, index=False)

def submit_feedback():
    st.title("Submit Feedback")
    name = st.text_input("Your Name")
    feedback = st.text_area("Your Feedback")
    event = st.selectbox("Select Event", ["Tech Talk", "Workshop", "Concert", "Hackathon"])
    rating = st.slider("Rate the Event (1-5)", 1, 5, 3)
    
    if st.button("Submit"):
        df = load_feedback()
        df = pd.concat([df, pd.DataFrame([{ "name": name, "feedback": feedback, "event": str(event), "rating": rating, "response": "" }])], ignore_index=True)
        save_feedback(df)
        st.success("Feedback submitted successfully!")

def analyze_event_performance():
    st.title("Event Performance Prediction")
    df = load_feedback()
    
    if df.empty:
        st.write("No feedback available.")
        return
    
    event_selected = st.selectbox("Select Event to Analyze", df["event"].dropna().unique())
    event_feedback = df[df["event"] == event_selected]
    feedback_text = " ".join(event_feedback["feedback"].dropna().tolist())
    
    try:
        response = co.generate(model="command", prompt=f"Analyze feedback for {event_selected} and summarize event performance: {feedback_text}")
        prediction = response.generations[0].text
    except Exception as e:
        prediction = f"Error fetching prediction: {str(e)}"
    
    st.subheader(f"Predicted Event Performance for {str(event_selected)}")
    st.write(prediction)

def admin_dashboard():
    st.title("Admin Dashboard")
    password = st.text_input("Enter Admin Password", type="password")
    if password != "admin123":  # Simple authentication
        st.warning("Unauthorized access!")
        return
    
    df = load_feedback()
    
    if df.empty:
        st.write("No feedback to display.")
        return
    
    st.subheader("Feedback Overview")
    selected_event = st.selectbox("Select Event", df["event"].dropna().unique())
    event_feedback = df[df["event"] == selected_event]
    st.write(event_feedback)
    
    reply_option = st.radio("Do you want to reply to feedback?", ["No", "Yes"])
    
    if reply_option == "Yes":
        feedback_options = event_feedback[event_feedback["response"].isna() | (event_feedback["response"] == "")]
        if feedback_options.empty:
            st.write("No feedback available to reply.")
            return
        
        selected_feedback = st.selectbox("Select feedback to reply", feedback_options.index)
        row = df.loc[selected_feedback]
        
        st.subheader(f"Feedback from {row['name']} ({row['event']})")
        st.write(row["feedback"])
        
        response = st.text_area("Your Response")
        if st.button("Submit Response"):
            df.at[selected_feedback, "response"] = response
            save_feedback(df)
            st.success("Response submitted!")
            st.experimental_rerun()
    
    st.subheader("Delete Feedback")
    delete_option = st.radio("Do you want to delete a feedback?", ["No", "Yes"])
    
    if delete_option == "Yes":
        delete_feedback = st.selectbox("Select feedback to delete", event_feedback.index)
        if st.button("Delete Feedback"):
            df = df.drop(index=delete_feedback)
            save_feedback(df)
            st.success("Feedback deleted successfully!")
            st.experimental_rerun()
    
    # New Analytics Feature
    st.subheader("Analytics")
    st.write(f"Total feedback received for {selected_event}: {len(event_feedback)}")
    
    # Pie chart for ratings
    rating_counts = event_feedback["rating"].value_counts().sort_index()
    fig, ax = plt.subplots()
    ax.pie(rating_counts, labels=rating_counts.index, autopct='%1.1f%%', startangle=90, colors=["#ff9999","#66b3ff","#99ff99","#ffcc99","#c2c2f0"])
    ax.axis('equal')  # Equal aspect ratio ensures the pie chart is circular.
    st.pyplot(fig)

# Page navigation
page = st.sidebar.radio("Choose a Page", ["Submit Feedback", "Event Performance Prediction", "Admin Dashboard"])
if page == "Submit Feedback":
    submit_feedback()
elif page == "Event Performance Prediction":
    analyze_event_performance()
elif page == "Admin Dashboard":
    admin_dashboard()
