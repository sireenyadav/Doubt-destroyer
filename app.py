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
def categorize_comments_robust(comments, groq_key):
    """
    Upgraded Analyzer: Fixes 'Miscellaneous' bug by being smarter about JSON parsing.
    """
    client = Groq(api_key=groq_key)
    analyzed_results = []
    
    batch_size = 10
    
    # UI Elements
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_batches = len(comments) // batch_size + (1 if len(comments) % batch_size != 0 else 0)
    
    for i in range(0, len(comments), batch_size):
        batch = comments[i:i+batch_size]
        # We simplify the input to just ID and Text to save tokens
        batch_text = [{"id": idx, "text": c['text']} for idx, c in enumerate(batch)]
        
        # --- IMPROVED PROMPT ---
        prompt = f"""
        Classify these comments. 
        You MUST return a JSON object with a single key "data" containing a list.
        
        Categories:
        - "Doubt" (Questions, confusion, 'how to', 'why', '?')
        - "Praise" (Good video, thanks, OP, love you)
        - "Spam" (Attendance, random emojis, dates, self promo)
        - "Misc" (Anything else)

        Input comments: {json.dumps(batch_text)}
        
        REQUIRED OUTPUT FORMAT:
        {{ "data": [ {{ "id": 0, "category": "Doubt" }}, {{ "id": 1, "category": "Spam" }} ] }}
        """
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                completion = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.3-70b-versatile",
                    response_format={"type": "json_object"}
                )
                response_content = completion.choices[0].message.content
                response_data = json.loads(response_content)
                
                # --- SMART PARSER (The Fix) ---
                # It looks for ANY list in the response, not just 'results'
                results_list = []
                if "data" in response_data:
                    results_list = response_data["data"]
                elif "results" in response_data:
                    results_list = response_data["results"]
                else:
                    # If AI messed up keys, grab the first list we find
                    for val in response_data.values():
                        if isinstance(val, list):
                            results_list = val
                            break
                
                # Map back to original comments
                if results_list:
                    for res in results_list:
                        if res.get("id") is not None and res["id"] < len(batch):
                            full_comment = batch[res["id"]]
                            full_comment["category"] = res.get("category", "Misc")
                            analyzed_results.append(full_comment)
                    break # Success
                else:
                    raise Exception("No list found in AI response")

            except Exception as e:
                time.sleep(2) # Brief pause before retry
                if attempt == max_retries - 1:
                    # Final fail: Mark batch as Misc
                    for c in batch:
                        c["category"] = "Misc"
                        analyzed_results.append(c)

        # Update UI
        current = (i // batch_size) + 1
        progress_bar.progress(min(current / total_batches, 1.0))
        status_text.text(f"Analyzing batch {current}/{total_batches}...")
        time.sleep(0.5)
        
    status_text.success("Analysis Complete!")
    time.sleep(1)
    status_text.empty()
    progress_bar.empty()
    return analyzed_results
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
              
