def share_location(user_id, lat, lon, is_stall_owner, stall_name=None):
    try:
        response = proxy_to_backend(
            "/save-location",
            method="POST",
            json_data={
                "user_id": user_id,
                "latitude": lat,
                "longitude": lon,
                "is_stall_owner": is_stall_owner,
                "stall_name": stall_name
            }
        )
        if "error" in response:
            st.error(f"Failed to save location: {response['error']}")
            return False
        st.success("Location updated")
        return True
    except Exception as e:
        logger.error(f"Failed to save location: {str(e)}")
        st.error(f"Failed to save location: {str(e)}")
        return False