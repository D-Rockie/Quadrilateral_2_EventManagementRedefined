import streamlit as st
from streamlit_folium import folium_static
import folium

def main():
    st.title("Folium Map Demo")
    st.write("Enter coordinates to see them on the map!")

    col1, col2 = st.columns(2)
    with col1:
        latitude = st.number_input("Latitude", format="%.6f", value=37.7749)
    with col2:
        longitude = st.number_input("Longitude", format="%.6f", value=-122.4194)

    # Create and display map
    m = folium.Map(location=[latitude, longitude], zoom_start=12)
    folium.Marker([latitude, longitude], popup="Your Location", icon=folium.Icon(color="blue")).add_to(m)
    folium_static(m, width=600, height=400)

if __name__ == "__main__":
    main()