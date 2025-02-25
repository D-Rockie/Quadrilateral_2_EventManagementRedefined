import streamlit as st
from streamlit_option_menu import option_menu

def main():
    # Custom CSS for sidebar
    st.markdown("""
        <style>
            .sidebar .sidebar-content { background-color: #2c3e50; color: white; }
            .sidebar h2 { color: #ecf0f1; }
        </style>
    """, unsafe_allow_html=True)

    # Sidebar with Option Menu
    with st.sidebar:
        st.markdown("<h2>Navigation</h2>", unsafe_allow_html=True)
        page = option_menu(
            menu_title=None,
            options=["Home", "Events", "Settings"],
            icons=["house", "calendar", "gear"],
            default_index=0,
            styles={
                "container": {"padding": "0!important", "background-color": "#2c3e50"},
                "icon": {"color": "#ecf0f1", "font-size": "18px"},
                "nav-link": {"color": "#ecf0f1", "font-size": "16px", "text-align": "left", "margin": "0px", "--hover-color": "#3498db"},
                "nav-link-selected": {"background-color": "#3498db"},
            }
        )

    # Page content
    if page == "Home":
        st.title("Home Page")
        st.write("Welcome to the app!")
    elif page == "Events":
        st.title("Events Page")
        st.write("View your events here.")
    elif page == "Settings":
        st.title("Settings Page")
        st.write("Adjust your settings.")

if __name__ == "__main__":
    main()