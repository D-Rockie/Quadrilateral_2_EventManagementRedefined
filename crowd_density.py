def check_crowd_density():
    if not st.session_state.user_id or st.session_state.user_id == "unknown":
        st.error("Error: User ID is required to check crowd density.")
        return

    try:
        params = {"user_id": st.session_state.user_id}
        if st.session_state.get("last_location"):
            lat, lon = map(float, st.session_state.last_location.strip("()").split(","))
            params.update({"latitude": lat, "longitude": lon})

        response = proxy_to_backend("/crowd_density", method="GET", json_data=params)
        crowd_data = response if "error" not in response else get_stall_crowd_density()

        user_lat = lat if st.session_state.get("last_location") else 37.7749
        user_lon = lon if st.session_state.get("last_location") else -122.4194
        m = folium.Map(location=[user_lat, user_lon], zoom_start=13)

        if st.session_state.get("last_location"):
            folium.Marker(
                [user_lat, user_lon],
                popup="Your Location",
                icon=folium.Icon(color="green", icon="user")
            ).add_to(m)

        for stall_name, details in crowd_data.items():
            if isinstance(details, dict) and "latitude" in details and "longitude" in details and "crowd_count" in details:
                crowd_count = details["crowd_count"]
                color = "green" if crowd_count < 10 else "orange" if crowd_count < 20 else "red"
                popup_text = f"{stall_name}<br>Crowd Count: {crowd_count}"
                folium.Marker(
                    [details["latitude"], details["longitude"]],
                    popup=popup_text,
                    icon=folium.Icon(color=color, icon="info-sign")
                ).add_to(m)

        folium_static(m)

        if st.session_state.get("stall_registered", False) and st.session_state.get("stall_name"):
            stall_name = st.session_state.stall_name
            if stall_name in crowd_data:
                details = crowd_data[stall_name]
                st.success(f"Crowd Density for {stall_name}:")
                st.write(f"People Count: {details['crowd_count']}")
                st.write(f"Crowd Level: {'Low' if details['crowd_count'] < 10 else 'Medium' if details['crowd_count'] < 20 else 'High'}")
                st.write(f"Location: ({details['latitude']:.6f}, {details['longitude']:.6f})")
                chart_data = pd.DataFrame({"Stall": [stall_name], "People Count": [details["crowd_count"]]})
                st.bar_chart(chart_data.set_index("Stall"))
            else:
                st.warning(f"No crowd data available for your stall ({stall_name}).")
        else:
            if st.session_state.get("last_location"):
                nearby_stalls = {}
                for stall_name, details in crowd_data.items():
                    if isinstance(details, dict) and "latitude" in details and "longitude" in details:
                        distance = geodesic((user_lat, user_lon), (details["latitude"], details["longitude"])).meters
                        if distance <= 50:
                            nearby_stalls[stall_name] = details
                if nearby_stalls:
                    st.success("Crowd Density for Nearby Stalls:")
                    chart_data = pd.DataFrame({
                        "Stall": list(nearby_stalls.keys()),
                        "People Count": [details["crowd_count"] for details in nearby_stalls.values()]
                    })
                    st.bar_chart(chart_data.set_index("Stall"))
                    for stall_name, details in nearby_stalls.items():
                        st.write(f"- {stall_name}:")
                        st.write(f"  People Count: {details['crowd_count']}")
                        st.write(f"  Crowd Level: {'Low' if details['crowd_count'] < 10 else 'Medium' if details['crowd_count'] < 20 else 'High'}")
                        st.write(f"  Location: ({details['latitude']:.6f}, {details['longitude']:.6f})")
                else:
                    st.info("No stalls within 50 meters of your location.")
            else:
                st.info("Please update your location to see nearby crowd density.")
    except Exception as e:
        logger.error(f"Error checking crowd density: {str(e)}")
        st.error(f"Error fetching crowd density: {str(e)}")