import streamlit as st
import requests
import pandas as pd
import time  

# TikTok API URL (replace with your actual API endpoint)
API_URL = "https://api.douyin.wtf/api/tiktok/web/fetch_post_comment"

# Streamlit UI
st.title("TikTok Comments Scraper")

# User input for Video ID
AWEME_ID = st.text_input("Enter TikTok Video ID:", "7477926434300841224")

# User input for number of pages
num_pages = st.number_input("Enter the number of pages to scrape:", min_value=1, max_value=5000, value=10, step=1)

# Button to start fetching
if st.button("Fetch Comments"):
    cursor = 0  # Initial cursor
    all_comments = []  # Store fetched comments
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i in range(num_pages):  # Loop based on user input
        params = {
            "aweme_id": AWEME_ID,
            "cursor": cursor,
            "count": 50  # Fetch 50 comments per request
        }
        
        response = requests.get(API_URL, params=params)
        data = response.json()

        # Check if response contains comments
        if "data" in data and "comments" in data["data"]:
            comments = data["data"]["comments"]
            if not comments:
                st.warning(f"Empty response at cursor {cursor}, stopping...")
                break  

            # Extract required fields
            for comment in comments:
                all_comments.append({
                    "text": comment.get("text", ""),
                    "nickname": comment["user"].get("nickname", "Unknown"),
                    "create_time": comment.get("create_time", ""),
                    "digg_count": comment.get("digg_count", 0)
                })

            # Update progress
            total_fetched = len(all_comments)
            status_text.text(f"Fetched {total_fetched} comments...")
            progress_bar.progress(min(i / num_pages, 1.0))  

            # Update cursor for next request
            cursor = data["data"]["cursor"]

            # Stop fetching if no more comments
            if data["data"].get("has_more") == 0:
                st.success("No more comments available.")
                break
            
            time.sleep(1)  # Avoid rate limits
        else:
            st.error(f"Unexpected response at cursor {cursor}, stopping...")
            break

    # Convert to DataFrame and Display
    df = pd.DataFrame(all_comments)
    st.write(df)
    st.success(f"Scraping complete! {len(all_comments)} comments fetched.")

