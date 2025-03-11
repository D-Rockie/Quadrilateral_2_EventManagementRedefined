def get_eventbuddy_response(user_input, user_id, conversation_history):
    system_prompt = """
    You are EventBuddy, a cheerful and helpful AI assistant for EventHub, created by xAI. Your goal is to assist users with a friendly, witty vibe, just like Grok! Tasks include:
    1. Register users for events (use register_for_event).
    2. Create events (use add_event with title, date, venue, description, category).
    3. Provide stall feedback (use load_feedback).
    4. Recommend events or stalls based on interests (use get_interest_based_events or recommend_stalls).
    5. Check crowd density for stalls (use check_crowd_density or get_stall_crowd_density).
    Respond naturally, offer clarifications, and use [FETCH_DATA] for dynamic data.
    """
    history = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history:
        history.append({"role": msg["role"], "content": msg["message"]})
    history.append({"role": "user", "content": user_input})

    try:
        response = co.chat.completions.create(
            model="llama3-8b-8192",
            messages=history,
            max_tokens=150,
            temperature=0.7
        )
        assistant_response = response.choices[0].message.content.strip()
        logger.info("Successfully fetched response from Groq API.")
    except Exception as e:
        logger.error(f"Groq API error: {str(e)}")
        return f"Oops! Couldn’t connect to the Groq API. Error: {str(e)}"

    return assistant_response