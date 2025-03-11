def suggest_best_stall(user_id):
    try:
        response = requests.post(f"{BACKEND_URL}/suggest_stall", json={"user_id": user_id}, timeout=10)
        if response.status_code == 200:
            suggestion = response.json()
            if "error" in suggestion:
                st.warning(suggestion["error"])
            else:
                st.markdown(f"""
                    <div class="suggestion-message">
                        Recommended Stall: {suggestion['stall']}<br>
                        Reason: {suggestion['reason']}
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.error(f"Error fetching stall suggestion. Status: {response.status_code}, Response: {response.text}")
    except requests.RequestException as e:
        st.error(f"Network error: {str(e)}")