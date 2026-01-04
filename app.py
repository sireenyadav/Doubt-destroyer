import streamlit as st
import json
import time
import html
import pandas as pd
import plotly.express as px
import re
from googleapiclient.discovery import build
from groq import Groq

# --- CONFIGURATION ---
st.set_page_config(page_title="Doubt Destroyer Pro", page_icon="🛡️", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .stStatus { border-left: 5px solid #FF4B4B; background-color: #f0f2f6; }
    div[data-testid="stMetricValue"] { font-size: 28px; font-weight: bold; }
    .big-font { font-size: 20px !important; }
    .success-box { padding: 15px; background-color: #d4edda; border-radius: 5px; color: #155724; }
    .warning-box { padding: 15px; background-color: #fff3cd; border-radius: 5px; color: #856404; }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE INITIALIZATION ---
if "analyzed_data" not in st.session_state:
    st.session_state.analyzed_data = None
if "video_meta" not in st.session_state:
    st.session_state.video_meta = None

# --- SIDEBAR ---
with st.sidebar:
    st.header("🛡️ Configuration")
    YOUTUBE_API_KEY = st.text_input("YouTube API Key", type="password")
    GROQ_API_KEY = st.text_input("Groq API Key", type="password")
    
    st.divider()
    max_scan = st.slider("Max Comments to Scan", 50, 1000, 200, step=50)
    st.info("💡 Tablet Mode: Keep limit under 300 for speed.")
    
    if st.button("🗑️ Clear Cache"):
        st.session_state.analyzed_data = None
        st.session_state.video_meta = None
        st.rerun()

# --- LOGIC FUNCTIONS ---

def get_video_meta(video_id, key):
    try:
        yt = build('youtube', 'v3', developerKey=key)
        res = yt.videos().list(part="snippet,statistics", id=video_id).execute()
        return res['items'][0] if res['items'] else None
    except: return None

def clean_text(text):
    if not text: return ""
    text = html.unescape(text)
    text = text.replace("<br>", " ").replace("<b>", "").replace("</b>", "")
    return text

def extract_timestamps(text):
    # Regex to find timestamps like 12:30, 1:20:05
    pattern = r'\b(?:\d{1,2}:)?\d{1,2}:\d{2}\b'
    matches = re.findall(pattern, text)
    return matches[0] if matches else None

def generate_ai_insights(df, groq_key):
    """Generates the Next Video Prediction and Auto-Description using LLM"""
    client = Groq(api_key=groq_key)
    
    # Filter only doubts for analysis
    doubts = df[df['category'] == 'Doubt']['text'].tolist()
    doubts_text = "\n".join([f"- {d}" for d in doubts[:30]]) # Limit to top 30 for prompt context
    
    if not doubts:
        return None

    prompt = f"""
    Analyze these student doubts from a YouTube educational video:
    {doubts_text}

    TASK:
    Return a JSON object with two keys:
    1. "next_video_idea": A title for a new video that solves the most common confusion here.
    2. "next_video_reason": Why this video is needed (e.g., "15 students asked about X").
    3. "faq_list": A list of top 3 questions with brief 1-sentence draft answers.
    """
    
    try:
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"}
        )
        return json.loads(completion.choices[0].message.content)
    except:
        return None

def deep_analyze(video_id, yt_key, groq_key, limit):
    yt = build('youtube', 'v3', developerKey=yt_key)
    client = Groq(api_key=groq_key)
    
    results = []
    next_token = None
    fetched_count = 0
    
    status = st.status("🚀 Processing Video Intelligence...", expanded=True)
    log = status.empty()
    bar = status.progress(0)
    
    try:
        while fetched_count < limit:
            log.write(f"📥 Fetching comments... ({fetched_count}/{limit})")
            req = yt.commentThreads().list(
                part="snippet", videoId=video_id, maxResults=50, 
                pageToken=next_token, order="relevance"
            )
            res = req.execute()
            
            raw_batch = []
            for item in res.get('items', []):
                snippet = item['snippet']['topLevelComment']['snippet']
                clean_comment = clean_text(snippet['textDisplay'])
                
                raw_batch.append({
                    "author": snippet['authorDisplayName'],
                    "text": clean_comment,
                    "likes": snippet['likeCount'],
                    "date": snippet['publishedAt'][:10],
                    "timestamp": extract_timestamps(clean_comment)
                })
            
            if not raw_batch: break
            fetched_count += len(raw_batch)
            
            # ANALYZE BATCH
            chunk_mini = [{"id": i, "text": c['text']} for i, c in enumerate(raw_batch)]
            
            prompt = f"""
            Classify these comments for a teacher's analytics dashboard.
            Categories: "Doubt" (conceptual questions), "Spam" (irrelevant/promotion), "Praise" (thanks/good job), "Misc".
            Also extract a 2-3 word "Topic" if it is a Doubt (e.g., "Thermodynamics", "Calculus").
            
            Input: {json.dumps(chunk_mini)}
            Return JSON: {{ "data": [ {{ "id": 0, "category": "Doubt", "topic": "Entropy" }} ] }}
            """
            
            try:
                completion = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.3-70b-versatile",
                    response_format={"type": "json_object"}
                )
                ai_data = json.loads(completion.choices[0].message.content)
                parsed = ai_data.get("data", [])
                
                for p in parsed:
                    idx = p.get("id")
                    if idx is not None and idx < len(raw_batch):
                        raw_batch[idx]['category'] = p.get('category', 'Misc')
                        raw_batch[idx]['topic'] = p.get('topic', 'N/A')
                        results.append(raw_batch[idx])
                        
            except Exception as e:
                pass # Skip batch on error to keep moving
                
            bar.progress(min(fetched_count / limit, 1.0))
            next_token = res.get('nextPageToken')
            if not next_token: break
            
        status.update(label="✅ Analysis Complete!", state="complete", expanded=False)
        return results

    except Exception as e:
        status.error(f"Error: {e}")
        return []

# --- MAIN UI ---
st.title("🛡️ Doubt Destroyer Pro")
st.caption("Turn Comments into Content & Revenue")

col1, col2 = st.columns([3, 1])
url = col1.text_input("Paste YouTube Video URL:", placeholder="https://youtube.com/watch?v=...")
analyze_btn = col2.button("🚀 Analyze Now", use_container_width=True, type="primary")

if analyze_btn and url and YOUTUBE_API_KEY and GROQ_API_KEY:
    # Reset state for new analysis
    st.session_state.analyzed_data = None
    st.session_state.video_meta = None
    
    vid_id = url.split("v=")[1].split("&")[0] if "v=" in url else url.split("/")[-1].split("?")[0]
    meta = get_video_meta(vid_id, YOUTUBE_API_KEY)
    
    if meta:
        st.session_state.video_meta = meta
        raw_data = deep_analyze(vid_id, YOUTUBE_API_KEY, GROQ_API_KEY, max_scan)
        if raw_data:
            df = pd.DataFrame(raw_data)
            # Generate AI Insights immediately
            insights = generate_ai_insights(df, GROQ_API_KEY)
            st.session_state.analyzed_data = {"df": df, "insights": insights}
        else:
            st.error("No comments found.")

# --- DASHBOARD DISPLAY ---
if st.session_state.analyzed_data and st.session_state.video_meta:
    meta = st.session_state.video_meta
    df = st.session_state.analyzed_data['df']
    insights = st.session_state.analyzed_data['insights']
    
    # 1. HEADER & METRICS
    st.divider()
    c1, c2 = st.columns([1, 4])
    c1.image(meta['snippet']['thumbnails']['medium']['url'], width=200)
    with c2:
        st.subheader(meta['snippet']['title'])
        
        # Calculates Metrics
        total = len(df)
        doubts = len(df[df['category'] == 'Doubt'])
        confusion_rate = int((doubts / total) * 100) if total > 0 else 0
        video_iq = 100 - confusion_rate
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Video IQ Score", f"{video_iq}/100", delta="Quality Metric")
        m2.metric("Confusion Rate", f"{confusion_rate}%", delta_color="inverse")
        m3.metric("Doubts Found", doubts)
        m4.metric("Total Scanned", total)

    # 2. FEATURE TABS
    st.divider()
    tab1, tab2, tab3 = st.tabs(["🔮 Next Video Predictor", "📝 Auto-Description", "🛡️ Doubt Database"])
    
    with tab1:
        st.markdown("### 🚀 High-Demand Content Opportunities")
        
        if insights and insights.get('next_video_idea'):
            st.success(f"**Recommended Next Video:** {insights['next_video_idea']}")
            st.info(f"**Why?** {insights['next_video_reason']}")
        else:
            st.warning("Not enough data to predict next video yet.")
            
        st.markdown("#### Top Confusion Topics")
        topic_counts = df[df['category'] == 'Doubt']['topic'].value_counts().reset_index()
        topic_counts.columns = ['Topic', 'Count']
        topic_counts = topic_counts[topic_counts['Topic'] != 'N/A']
        
        if not topic_counts.empty:
            fig = px.bar(topic_counts.head(7), x='Count', y='Topic', orientation='h', title="Top Doubt Themes", color='Count')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.write("No specific topics detected.")

    with tab2:
        st.markdown("### 📋 Copy-Paste Description")
        st.markdown("Use this to boost SEO and answer questions instantly.")
        
        # Generate Markdown for Description
        desc_md = "### 📌 Top Doubts & Answers\n\n"
        
        if insights and insights.get('faq_list'):
            for i, faq in enumerate(insights['faq_list']):
                desc_md += f"**Q: {faq['Question']}**\n\n" if 'Question' in faq else f"**Q{i+1}: ...**\n"
                desc_md += f"A: {faq['Answer']} _(Draft)_\n\n" if 'Answer' in faq else ""
        
        # Timestamps
        timestamps = df[df['timestamp'].notnull()]
        if not timestamps.empty:
            desc_md += "\n### ⏱️ Key Moments (User Mentioned)\n"
            # Get unique timestamps top 5
            unique_ts = timestamps['timestamp'].unique()[:5]
            for ts in unique_ts:
                desc_md += f"{ts} - Important Segment\n"
        
        st.code(desc_md, language="markdown")
        
    with tab3:
        st.markdown("### 🔍 Filter & Reply")
        filter_opt = st.radio("Show:", ["Doubts Only", "All Comments"], horizontal=True)
        
        view_df = df[df['category'] == 'Doubt'] if filter_opt == "Doubts Only" else df
        
        for i, row in view_df.iterrows():
            with st.expander(f"{'❓' if row['category']=='Doubt' else '💬'} {row['author']} - {row['date']}"):
                st.write(row['text'])
                if row['category'] == 'Doubt':
                    st.caption(f"Topic: {row['topic']}")
                    st.button("Generate Reply", key=f"rep_{i}")

elif url and (not YOUTUBE_API_KEY or not GROQ_API_KEY):
    st.warning("⚠️ Please enter your API Keys in the sidebar to start.")
            
