import streamlit as st
import json
import time
import pandas as pd
import plotly.express as px
from googleapiclient.discovery import build
from groq import Groq

# --- CONFIGURATION ---
st.set_page_config(page_title="Doubt Destroyer Deep Scan", page_icon="🕵️", layout="wide")

# --- CSS FOR "BEAUTIFUL" UI ---
st.markdown("""
<style>
    .stStatus { border-left: 5px solid #FF4B4B; background-color: #f0f2f6; }
    div[data-testid="stMetricValue"] { font-size: 24px; }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.header("🕵️ Deep Scan Setup")
    st.markdown("Analyze **100%** of the comments on a specific video.")
    
    YOUTUBE_API_KEY = st.text_input("YouTube API Key", type="password")
    GROQ_API_KEY = st.text_input("Groq API Key", type="password")
    
    st.divider()
    
    # User Control
    max_scan = st.slider("Max Comments Limit", 100, 3000, 500, step=100)
    st.caption("⚠️ Scanning 1000 comments takes ~2-3 minutes.")

# --- LOGIC ---

def get_video_meta(video_id, key):
    """Get Thumbnail and Title"""
    try:
        yt = build('youtube', 'v3', developerKey=key)
        res = yt.videos().list(part="snippet,statistics", id=video_id).execute()
        return res['items'][0] if res['items'] else None
    except: return None

def deep_analyze(video_id, yt_key, groq_key, limit):
    """
    The Core Engine: Fetches & Analyzes in a stream.
    Includes 'Beautiful Progress' logic.
    """
    yt = build('youtube', 'v3', developerKey=yt_key)
    client = Groq(api_key=groq_key)
    
    results = []
    next_token = None
    fetched_count = 0
    
    # --- BEAUTIFUL PROGRESS CONTAINER ---
    status = st.status("🚀 Starting Deep Scan...", expanded=True)
    progress_bar = status.progress(0)
    log_area = status.empty() # Placeholder for scrolling text
    
    try:
        # 1. LOOP UNTIL LIMIT REACHED
        while fetched_count < limit:
            # A. FETCH FROM YOUTUBE
            log_area.markdown(f"**📥 Fetching comments... ({fetched_count}/{limit})**")
            req = yt.commentThreads().list(
                part="snippet", videoId=video_id, maxResults=100, 
                pageToken=next_token, order="relevance"
            )
            res = req.execute()
            
            raw_batch = []
            for item in res.get('items', []):
                snippet = item['snippet']['topLevelComment']['snippet']
                raw_batch.append({
                    "author": snippet['authorDisplayName'],
                    "text": snippet['textDisplay'],
                    "likes": snippet['likeCount'],
                    "date": snippet['publishedAt'][:10]
                })
            
            if not raw_batch: break # No more comments
            fetched_count += len(raw_batch)
            
            # B. ANALYZE WITH GROQ (Chunks of 15)
            chunk_size = 15
            for i in range(0, len(raw_batch), chunk_size):
                chunk = raw_batch[i:i+chunk_size]
                chunk_mini = [{"id": x, "text": c['text']} for x, c in enumerate(chunk)]
                
                # STRICT PROMPT
                prompt = f"""
                Classify these comments for a teacher dashboard.
                1. "Doubt": MUST be a specific SUBJECT QUESTION (Physics/Math). IGNORE "Batch 2025", "When is class?".
                2. "Spam": "Attendance", "Like if", "Who is watching", emojis, dates.
                3. "Praise": "Best teacher", "OP", "Thanks".
                4. "Misc": Anything else.
                
                Input: {json.dumps(chunk_mini)}
                Return JSON: {{ "data": [ {{ "id": 0, "category": "Doubt" }} ] }}
                """
                
                # RETRY LOGIC (The "Unbreakable" Part)
                for attempt in range(3):
                    try:
                        log_area.markdown(f"🧠 **Analyzing batch...** (Processed {len(results)} comments so far)")
                        completion = client.chat.completions.create(
                            messages=[{"role": "user", "content": prompt}],
                            model="llama-3.3-70b-versatile",
                            response_format={"type": "json_object"}
                        )
                        ai_data = json.loads(completion.choices[0].message.content)
                        
                        # Parser
                        data_list = ai_data.get("data", ai_data.get("results", []))
                        if not data_list: # Fallback
                             for v in ai_data.values(): 
                                 if isinstance(v, list): data_list = v; break
                        
                        if data_list:
                            for d in data_list:
                                if d.get("id") is not None and d["id"] < len(chunk):
                                    chunk[d["id"]]["category"] = d.get("category", "Misc")
                                    results.append(chunk[d["id"]])
                            break # Success
                            
                    except Exception as e:
                        if "429" in str(e):
                            wait = (2 ** attempt) + 1
                            log_area.warning(f"⚠️ API Hot! Cooling down for {wait}s...")
                            time.sleep(wait)
                        else:
                            break 
                
                # Update Progress Bar
                progress_bar.progress(min(fetched_count / limit, 1.0))
            
            # Check Next Page
            next_token = res.get('nextPageToken')
            if not next_token: break
            
        status.update(label="✅ Deep Scan Complete!", state="complete", expanded=False)
        return results

    except Exception as e:
        status.error(f"Error: {e}")
        return []

# --- MAIN UI ---
st.title("🎓 Doubt Destroyer: Single Video Deep Scan")

# Input Area
col1, col2 = st.columns([3, 1])
url = col1.text_input("Paste Video URL:")
start_btn = col2.button("🚀 Analyze", use_container_width=True)

if start_btn and url and YOUTUBE_API_KEY and GROQ_API_KEY:
    # 1. Parse ID
    vid_id = url.split("v=")[1].split("&")[0] if "v=" in url else url.split("/")[-1].split("?")[0]
    
    # 2. Get Info
    meta = get_video_meta(vid_id, YOUTUBE_API_KEY)
    
    if meta:
        st.divider()
        c1, c2 = st.columns([1, 3])
        c1.image(meta['snippet']['thumbnails']['high']['url'])
        c2.subheader(meta['snippet']['title'])
        c2.caption(f"Channel: {meta['snippet']['channelTitle']} | 💬 Total Comments: {meta['statistics']['commentCount']}")
        
        # 3. Run Analysis
        data = deep_analyze(vid_id, YOUTUBE_API_KEY, GROQ_API_KEY, max_scan)
        
        # 4. Dashboard
        if data:
            df = pd.DataFrame(data)
            st.divider()
            
            # Summary Metrics
            m1, m2, m3 = st.columns(3)
            m1.metric("Doubts Found", len(df[df['category'] == 'Doubt']), delta="High Priority")
            m2.metric("Spam Filtered", len(df[df['category'] == 'Spam']), delta_color="inverse")
            m3.metric("Praise", len(df[df['category'] == 'Praise']))
            
            # Pie Chart
            st.subheader("📊 Comment Distribution")
            fig = px.pie(df, names='category', hole=0.4, color='category',
                         color_discrete_map={"Doubt":"#ff4b4b", "Praise":"#00cc96", "Spam":"#636efa", "Misc":"#d3d3d3"})
            st.plotly_chart(fig, use_container_width=True)
            
            # Details Tabs
            tab1, tab2, tab3 = st.tabs(["🔥 Actionable Doubts", "📂 Full Data", "💾 Export"])
            
            with tab1:
                doubts = df[df['category'] == 'Doubt']
                if doubts.empty:
                    st.info("No doubts found. The strict filter is working!")
                for _, row in doubts.iterrows():
                    with st.expander(f"❓ {row['author']} ({row['date']})"):
                        st.write(f"**Question:** {row['text']}")
                        st.button("Draft Reply", key=row['text'][:15])
                        
            with tab2:
                st.dataframe(df)
                
            with tab3:
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("Download CSV Report", csv, "analysis.csv", "text/csv")
        else:
            st.warning("No comments found.")
            
