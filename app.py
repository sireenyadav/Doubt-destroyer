import streamlit as st
import json
import time
import random
import plotly.express as px
from googleapiclient.discovery import build
from groq import Groq

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Doubt Destroyer Pro",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. SESSION STATE (Keeps data alive when you click buttons) ---
if 'data_fetched' not in st.session_state:
    st.session_state.data_fetched = False
if 'analyzed_data' not in st.session_state:
    st.session_state.analyzed_data = []
if 'video_stats' not in st.session_state:
    st.session_state.video_stats = {}

# --- 3. SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.title("⚙️ Control Room")
    st.markdown("Enter your API keys to start the engine.")
    
    YOUTUBE_API_KEY = st.text_input("YouTube API Key", type="password")
    GROQ_API_KEY = st.text_input("Groq API Key", type="password")
    
    st.divider()
    
    # Slider for "Deep Scan" vs "Quick Scan"
    scan_limit = st.slider(
        "Comments to Analyze", 
        min_value=50, 
        max_value=300, 
        value=100, 
        step=50,
        help="Higher limits take longer. 100 is recommended for Free Tier."
    )
    
    st.info(f"⚡ Est. Processing Time: {scan_limit // 10 * 1.5:.0f} seconds")

# --- 4. CORE FUNCTIONS ---

def get_video_stats(video_id, api_key):
    """Fetches Video Metadata (Views, Likes, Channel Name)"""
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        request = youtube.videos().list(part="snippet,statistics", id=video_id)
        response = request.execute()
        if response['items']:
            item = response['items'][0]
            return {
                "title": item['snippet']['title'],
                "channel": item['snippet']['channelTitle'],
                "views": int(item['statistics'].get('viewCount', 0)),
                "likes": int(item['statistics'].get('likeCount', 0)),
                "comment_count": int(item['statistics'].get('commentCount', 0)),
                "thumbnail": item['snippet']['thumbnails']['high']['url']
            }
    except Exception as e:
        st.error(f"Error fetching stats: {e}")
        return None

def get_comments(video_id, api_key, limit=100):
    """Fetches comments from YouTube with Pagination"""
    youtube = build('youtube', 'v3', developerKey=api_key)
    comments = []
    next_page_token = None
    
    try:
        while len(comments) < limit:
            request = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=100,
                pageToken=next_page_token,
                order="relevance" # Gets top comments first (usually better quality)
            )
            response = request.execute()
            
            for item in response.get('items', []):
                snippet = item['snippet']['topLevelComment']['snippet']
                comments.append({
                    "author": snippet['authorDisplayName'],
                    "text": snippet['textDisplay'],
                    "likes": snippet['likeCount'],
                    "published": snippet['publishedAt'][:10]
                })
            
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break 
                
        return comments[:limit]
    except Exception as e:
        st.error(f"YouTube API Error: {e}")
        return []

def categorize_comments_robust(comments, groq_key):
    """
    The 'Unbreakable' Analyzer.
    Uses Exponential Backoff to handle Groq Rate Limits (Error 429).
    """
    client = Groq(api_key=groq_key)
    analyzed_results = []
    
    # Batch size of 10 is safe for Free Tier TPM limits
    batch_size = 10
    
    # UI Elements for Progress
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_batches = len(comments) // batch_size + (1 if len(comments) % batch_size != 0 else 0)
    
    for i in range(0, len(comments), batch_size):
        batch = comments[i:i+batch_size]
        batch_text = [{"id": idx, "text": c['text']} for idx, c in enumerate(batch)]
        
        # STRICT PROMPT
        prompt = f"""
        You are an Educational Data Analyst. Classify these YouTube comments.
        
        CATEGORIES:
        1. "Doubt": Genuine academic questions, confusion, "why/how", "samajh nahi aaya".
        2. "Praise": "Best teacher", "Thank you", "Love you", "OP".
        3. "Spam": "Attendance", "Like if you agree", emojis only, self-promotion.
        4. "Misc": Everything else.

        Input: {json.dumps(batch_text)}
        
        RETURN JSON: {{ "results": [ {{"id": 0, "category": "Doubt"}}, ... ] }}
        """
        
        # RETRY LOGIC (Exponential Backoff)
        max_retries = 5
        for attempt in range(max_retries):
            try:
                completion = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.3-70b-versatile",
                    response_format={"type": "json_object"}
                )
                response_data = json.loads(completion.choices[0].message.content)
                
                if "results" in response_data:
                    for res in response_data["results"]:
                        if res["id"] < len(batch):
                            full_comment = batch[res["id"]]
                            full_comment["category"] = res["category"]
                            analyzed_results.append(full_comment)
                break # Success! Exit retry loop.
                
            except Exception as e:
                error_msg = str(e)
                # If Rate Limit (429) -> Wait and Retry
                if "429" in error_msg or "rate limit" in error_msg.lower():
                    wait_time = (2 ** attempt) + random.uniform(0, 1) # 2s, 4s, 8s...
                    status_text.warning(f"⚠️ Rate limit hit. Cooling down for {wait_time:.1f}s...")
                    time.sleep(wait_time)
                else:
                    # Other Error -> Skip batch
                    for c in batch:
                        c["category"] = "Misc"
                        analyzed_results.append(c)
                    break 

        # Update Progress
        current_batch_num = (i // batch_size) + 1
        progress_bar.progress(min(current_batch_num / total_batches, 1.0))
        status_text.text(f"Analyzed {len(analyzed_results)}/{len(comments)} comments...")
        
        # Pacing: Sleep 1s to be gentle on the API
        time.sleep(1)
        
    status_text.success("Analysis Complete!")
    time.sleep(1)
    status_text.empty() # Clear the status text
    progress_bar.empty() # Clear the bar
    return analyzed_results

# --- 5. MAIN DASHBOARD UI ---

st.title("🎓 Doubt Destroyer")
st.markdown("### Turn Noise into Knowledge")
st.markdown("Filter out thousands of *'OP Sir'* comments to find the **10 students who actually need help**.")

# Input Section
col1, col2 = st.columns([3, 1])
with col1:
    video_url = st.text_input("Paste YouTube Video URL:", placeholder="https://youtu.be/...")
with col2:
    analyze_btn = st.button("🚀 Analyze Video", use_container_width=True)

# LOGIC FLOW
if analyze_btn:
    if not video_url or not YOUTUBE_API_KEY or not GROQ_API_KEY:
        st.error("⚠️ Please enter Video URL and BOTH API Keys in the sidebar.")
    else:
        # Smart URL Parsing
        video_id = None
        if "youtu.be" in video_url:
            video_id = video_url.split("/")[-1].split("?")[0]
        elif "v=" in video_url:
            video_id = video_url.split("v=")[1].split("&")[0]
            
        if video_id:
            # 1. Fetch Stats
            st.session_state.video_stats = get_video_stats(video_id, YOUTUBE_API_KEY)
            
            # 2. Fetch Comments
            with st.spinner(f"📥 Fetching top {scan_limit} comments from YouTube..."):
                raw_comments = get_comments(video_id, YOUTUBE_API_KEY, limit=scan_limit)
            
            # 3. Analyze with AI
            if raw_comments:
                with st.spinner("🧠 AI is separating Doubts from Spam (This may take a moment)..."):
                    st.session_state.analyzed_data = categorize_comments_robust(raw_comments, GROQ_API_KEY)
                    st.session_state.data_fetched = True
            else:
                st.warning("No comments found or API error.")
        else:
            st.error("Invalid YouTube URL.")

# --- 6. DISPLAY RESULTS ---
if st.session_state.data_fetched:
    stats = st.session_state.video_stats
    data = st.session_state.analyzed_data
    
    # METRICS ROW
    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Views", f"{stats['views']:,}")
    c2.metric("Likes", f"{stats['likes']:,}")
    c3.metric("Total Comments", f"{stats['comment_count']:,}")
    c4.metric("Scanned", len(data))
    
    # CHART ROW
    st.divider()
    col_chart, col_thumb = st.columns([2, 1])
    
    with col_chart:
        st.subheader("📊 Comment Distribution")
        cat_counts = {}
        for d in data:
            cat = d.get('category', 'Misc')
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
        
        # Color Map for consistency
        colors = {"Doubt": "#FF4B4B", "Praise": "#00CC96", "Spam": "#636EFA", "Misc": "#FFA15A"}
        
        fig = px.pie(
            values=list(cat_counts.values()), 
            names=list(cat_counts.keys()), 
            hole=0.4,
            color=list(cat_counts.keys()),
            color_discrete_map=colors
        )
        st.plotly_chart(fig, use_container_width=True)
        
    with col_thumb:
        st.image(stats['thumbnail'], caption=stats['title'], use_column_width=True)

    # TABS SECTION
    st.divider()
    tab_doubt, tab_praise, tab_spam, tab_raw = st.tabs(["🔥 ACTIONABLE DOUBTS", "💖 Praise", "🚫 Spam/Engagement", "📂 All Data"])
    
    with tab_doubt:
        doubts = [d for d in data if d['category'] == 'Doubt']
        if doubts:
            st.success(f"Found {len(doubts)} High-Value Doubts")
            for i, d in enumerate(doubts):
                with st.expander(f"❓ {d['author']}: {d['text'][:60]}..."):
                    st.write(f"**Full Question:** {d['text']}")
                    st.caption(f"👍 Likes: {d['likes']} | 📅 {d['published']}")
                    
                    # Draft Reply Action
                    if st.button(f"Draft Reply #{i}"):
                        st.text_area("AI Draft (Copy this)", value=f"Hello {d['author']}, great question! \n[ AI would generate answer here based on transcript ]\nKeep studying!", height=100)
        else:
            st.info("No doubts found in this batch! The students must be geniuses.")

    with tab_praise:
        praise = [d for d in data if d['category'] == 'Praise']
        st.info(f"{len(praise)} Positive Comments")
        st.dataframe(praise, column_config={"author": "Student", "text": "Comment", "likes": "Likes"}, height=300)

    with tab_spam:
        spam = [d for d in data if d['category'] == 'Spam']
        st.warning(f"{len(spam)} Spam/Engagement Comments")
        st.dataframe(spam, column_config={"author": "User", "text": "Spam Content"}, height=300)
            
    with tab_raw:
        st.dataframe(data)
              
