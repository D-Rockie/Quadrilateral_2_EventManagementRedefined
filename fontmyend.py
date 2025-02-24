import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# Flask backend URL
BACKEND_URL = "http://127.0.0.1:5000"

# Custom CSS for styling
st.markdown("""
    <style>
    .crowd-level {
        padding: 10px;
        margin: 5px;
        border-radius: 5px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .very-low { background-color: #e0f7e9; color: #006400; }
    .low { background-color: #b3e6b3; color: #006400; }
    .medium { background-color: #fff9e6; color: #8b4513; }
    .high { background-color: #ffe6e6; color: #ff4500; }
    .very-high { background-color: #ffcccc; color: #ff0000; }
    .crowd-icon { margin-right: 10px; font-size: 20px; }
    </style>
    """, unsafe_allow_html=True)

st.title("Stall Crowd Monitor")

# Get user ID
user_id = st.text_input("Enter your User ID:", key="user_id")

# Ask if the user is a stall owner
is_stall_owner = st.checkbox("I am a stall owner", key="stall_owner")

stall_name = ""
if is_stall_owner:
    stall_name = st.text_input("Enter your Stall Name:", key="stall_name")

# Use columns to place latitude and longitude side by side
col1, col2 = st.columns(2)
with col1:
    latitude = st.number_input("Enter Latitude:", format="%.6f", key="latitude")
with col2:
    longitude = st.number_input("Enter Longitude:", format="%.6f", key="longitude")

if st.button("Share Location"):
    if not user_id or not latitude or not longitude:
        st.error("User ID, Latitude, and Longitude are required!")
    else:
        try:
            data = {
                "user_id": user_id,
                "latitude": latitude,
                "longitude": longitude,
                "is_stall_owner": is_stall_owner,
                "stall_name": stall_name if is_stall_owner else ""
            }
            response = requests.post(f"{BACKEND_URL}/update_location", json=data, timeout=10)
            if response.status_code == 200:
                st.success("Location shared successfully!")
            else:
                st.error(f"Error: {response.json().get('error', 'Unknown error')}")
        except requests.RequestException as e:
            st.error(f"Network error: {str(e)}")
        except Exception as e:
            st.error(f"Unexpected error: {str(e)}")

if st.button("Check Crowd Density"):
    try:
        response = requests.get(f"{BACKEND_URL}/crowd_density", timeout=10)
        if response.status_code == 200:
            crowd_data = response.json()
            if "error" in crowd_data:
                st.info(crowd_data["error"])
            else:
                st.markdown("### Crowd Levels")
                # Prepare data for bar chart
                stall_names = []
                crowd_counts = []
                for stall, details in crowd_data.items():
                    stall_names.append(stall)
                    crowd_counts.append(details["crowd_count"])
                    # Display styled crowd level
                    crowd_level = details["crowd_level"].lower().replace(" ", "-")
                    icon = "👥"  # Unicode people icon
                    st.markdown(f"""
                        <div class="crowd-level {crowd_level}">
                            <span class="crowd-icon">{icon}</span>
                            <span><strong>{stall}</strong>: {details['crowd_level']} ({details['crowd_count']} people)</span>
                        </div>
                    """, unsafe_allow_html=True)

                # Create a thinner, styled bar chart using Plotly
                fig = go.Figure(data=[
                    go.Bar(
                        x=stall_names,
                        y=crowd_counts,
                        marker_color=['#006400' if count <= 1 else '#b3e6b3' if count <= 3 else '#fff9e6' if count <= 5 else '#ffe6e6' if count <= 7 else '#ffcccc' for count in crowd_counts],  # Color based on crowd level
                        width=0.2  # Thinner bars
                    )
                ])
                fig.update_layout(
                    title="Crowd Count by Stall",
                    xaxis_title="Stalls",
                    yaxis_title="Number of People",
                    plot_bgcolor='white',
                    paper_bgcolor='white',
                    bargap=0.3,  # Gap between bars
                    bargroupgap=0.1,  # Gap within groups
                    font=dict(size=12, color='black'),
                    height=400,  # Chart height
                    width=600,  # Chart width
                    showlegend=False
                )
                st.plotly_chart(fig, use_container_width=True)

        else:
            st.error("Error fetching crowd density data.")
    except requests.RequestException as e:
        st.error(f"Network error: {str(e)}")
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")

# Add a note for users
st.write("**Note:** Use Google Maps or another mapping tool to find your latitude and longitude. For example, right-click a location on Google Maps and copy the coordinates.")