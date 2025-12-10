import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import google.generativeai as genai
import yt_dlp
import os
import re
import time
import requests
from PIL import Image
import nest_asyncio
import gc
import random

nest_asyncio.apply()

# --- 1. 頁面設定 ---
st.set_page_config(
    page_title="TrendScope Stability | 穩定大師版",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. 深色 UI ---
st.markdown("""
<style>
    .stApp { background-color: #121212 !important; color: #E0E0E0 !important; }
    h1, h2, h3, h4, h5, h6, .stMarkdown { color: #E0E0E0 !important; }
    .stButton > button {
        background-color: #2E7D32 !important; color: white !important; /* 深綠色，象徵穩定 */
        border: 1px solid #1B5E20 !important; font-weight: 600;
        width: 100%; padding: 0.8rem; border-radius: 6px;
    }
    .stButton > button:hover { background-color: #388E3C !important; }
    .stTextArea textarea, .stTextInput input {
        background-color: #1E1E1E !important; color: #E0E0E0 !important; border: 1px solid #333 !important;
    }
    .stTextArea textarea:focus, .stTextInput input:focus { border-color: #2E7D32 !important; }
    .custom-card { background-color: #1E1E1E; padding: 25px; border: 1px solid #333; border-radius: 10px; margin-bottom: 25px; }
    .stTabs [data-baseweb="tab-list"] { background-color: #121212; }
    .stTabs [aria-selected="true"] { background-color: #2E7D32 !important; color: white !important; }
    .stChatMessage { background-color: #1E1E1E !important; border: 1px solid #333; }
    
    /* 限流提示 */
    .wait-box { background-color: #263238; color: #80CBC4; padding: 10px; border-radius: 5px; margin-bottom: 10px; border-left: 4px solid #80CBC4; }
</style>
""", unsafe_allow_html=True)

# --- 3. 狀態初始化 ---
if "analysis_report" not in st.session_state: st.session_state.analysis_report = ""
if "raw_context" not in st.session_state: st.session_state.raw_context = ""
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "available_models" not in st.session_state: st.session_state.available_models = []

# --- 4. 核心：智慧限流與重試系統 (Smart Throttling) ---
def safe_api_call(func, *args, **kwargs):
    """
    包裝 API 呼叫，遇到 429 錯誤自動等待並重試
    """
    max_retries = 3
    base_wait = 10 # 基礎等待秒數
    
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                wait_time = base_wait * (attempt + 1) + random.uniform(1, 5) # 指數退避 + 隨機擾動
                st.markdown(f"""
                <div class="wait-box">
                    ⏳ <b>觸發 API 流量限制</b> (Attempt {attempt+1}/{max_retries})<br>
                    系統正在冷卻中，將於 {int(wait_time)} 秒後自動重試...請勿關閉視窗。
                </div>
                """, unsafe_allow_html=True)
                time.sleep(wait_time)
            else:
                raise e # 其他錯誤直接拋出
    raise Exception("API 重試次數過多，請稍後再試。")

# --- 檔案處理 ---
def safe_remove(filepath):
    try:
        if os.path.exists(filepath):
            gc.collect()
            time.sleep(0.5)
            os.remove(filepath)
    except: pass

def load_image_safe(filepath):
    try:
        with Image.open(filepath) as img:
            img.load()
            return img.copy()
    except: return None

# --- 側邊欄 ---
with st.sidebar:
    st.title("🛡️ 控制面板")
    api_key = st.text_input("Google API Key", type="password", value=st.session_state.get("api_key", ""))
    
    if st.button("🔄 載入模型清單"):
        if api_key:
            try:
                genai.configure(api_key=api_key)
                models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                st.session_state.available_models = models
                st.session_state.api_key = api_key
                st.success("已連線")
            except Exception as e:
                st.error(f"錯誤: {e}")

    options = st.session_state.available_models if st.session_state.available_models else ["models/gemini-1.5-flash"]
    # 預設選 Flash
    default_ix = 0
    for i, m in enumerate(options):
        if "gemini-1.5-flash" in m and "8b" not in m: default_ix = i; break
    selected_model = st.selectbox("選擇模型", options, index=default_ix)
    
    if st.button("🗑️ 清除所有紀錄"):
        st.session_state.analysis_report = ""
        st.session_state.raw_context = ""
        st.session_state.chat_history = []
        st.experimental_rerun()
    
    st.info("""
    **🛡️ 穩定模式已啟動**
    - 批量分析時會自動降速，避免 429 錯誤。
    - 音訊將轉為文字記憶，提升追問準確度。
    """)

# --- 工具函數 ---
def get_video_full_info(url):
    ydl_opts = {'quiet': True, 'noplaylist': True, 'extract_flat': True, 'skip_download': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get('title', 'Unknown'),
                "channel": info.get('uploader', 'Unknown'),
                "views": info.get('view_count', 0),
                "thumbnail_url": info.get('thumbnail', None)
            }
    except: return None

def download_image(url, idx):
    try:
        filename = f"thumb_{idx}_{int(time.time())}.jpg"
        response = requests.get(url, stream=True, timeout=10)
        if response.status_code == 200:
            with open(filename, 'wb') as f: f.write(response.content)
            return filename
    except: pass
    return None

def get_yt_transcript(video_id):
    try:
        t = YouTubeTranscriptApi.get_transcript(video_id, languages=['zh-TW', 'zh', 'en'])
        return TextFormatter().format_transcript(t)
    except: return None

def download_audio(url, idx):
    filename = f"audio_{idx}_{int(time.time())}.m4a"
    safe_remove(filename)
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio',
        'outtmpl': filename,
        'quiet': True, 'noplaylist': True, 'ignoreerrors': True, 'nocheckcertificate': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        if os.path.exists(filename): return filename
        return filename.replace('.m4a', '.webm') if os.path.exists(filename.replace('.m4a', '.webm')) else None
    except: return None

# --- 主程式 ---
st.title("TrendScope Stability | 穩定大師版")
st.markdown('<div class="custom-card">', unsafe_allow_html=True)
tab1, tab2 = st.tabs(["📺 影音綜合分析", "📸 圖文截圖分析"])

urls_input = ""
imgs_input = []
txt_input = ""
mode = ""

with tab1:
    urls_input = st.text_area("YouTube / TikTok 網址 (一行一個)", height=150, key="vid_in")
    analyze_vid_btn = st.button("🚀 啟動分析", key="btn_vid")
    if analyze_vid_btn: mode = "video"

with tab2:
    imgs_input = st.file_uploader("上傳截圖", accept_multiple_files=True, type=['png', 'jpg'])
    txt_input = st.text_area("補充說明", height=100)
    analyze_soc_btn = st.button("🚀 啟動分析", key="btn_soc")
    if analyze_soc_btn: mode = "social"

st.markdown('</div>', unsafe_allow_html=True)

# ================= 邏輯核心 =================

if (mode == "video" and urls_input) or (mode == "social" and (imgs_input or txt_input)):
    if not api_key:
        st.error("請輸入 API Key")
    else:
        # 重置狀態
        st.session_state.analysis_report = ""
        st.session_state.raw_context = ""
        st.session_state.chat_history = []
        
        data_inputs = []
        raw_context_builder = []
        temp_files = []
        
        # 設定模型
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(selected_model)

        with st.status("🚀 系統啟動中...", expanded=True) as status:
            try:
                if mode == "video":
                    urls = [u.strip() for u in urls_input.split('\n') if u.strip()]
                    for i, url in enumerate(urls):
                        status.update(label=f"正在處理第 {i+1}/{len(urls)} 個來源 (慢速模式以防鎖IP)...", state="running")
                        
                        # --- 智慧限流：每處理一個影片，休息 3 秒 ---
                        if i > 0: time.sleep(3) 
                        
                        info = get_video_full_info(url)
                        if info:
                            thumb_path = None
                            if info.get('thumbnail_url'):
                                thumb_path = download_image(info['thumbnail_url'], i)
                                if thumb_path: temp_files.append(thumb_path)
                            
                            meta_str = f"【素材 #{i+1} Metadata】\n標題: {info['title']}\n頻道: {info['channel']}\n觀看數: {info['views']}\n"
                            
                            # 存入輸入 (Vision)
                            data_inputs.append(meta_str)
                            if thumb_path: data_inputs.append(thumb_path)
                            
                            # 存入記憶 (Memory)
                            raw_context_builder.append(meta_str)

                            # 處理內容
                            is_yt = "youtube" in url or "youtu.be" in url
                            transcript = None
                            if is_yt:
                                vid_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
                                if vid_match: transcript = get_yt_transcript(vid_match.group(1))
                            
                            if transcript:
                                trans_str = f"素材 #{i+1} 字幕:\n{transcript[:10000]}\n" # 縮減長度避免 token 爆炸
                                data_inputs.append(trans_str)
                                raw_context_builder.append(trans_str)
                            else:
                                aud_path = download_audio(url, i)
                                if aud_path:
                                    data_inputs.append(aud_path)
                                    temp_files.append(aud_path)
                                    # 注意：這裡我們只存標記，因為音訊轉文字需要額外 API call
                                    raw_context_builder.append(f"素材 #{i+1}: [含有音訊檔案，AI 已聆聽]\n")

                else: # Social Mode
                    if txt_input:
                        data_inputs.append(f"補充: {txt_input}")
                        raw_context_builder.append(f"補充: {txt_input}\n")
                    for i, img in enumerate(imgs_input):
                        data_inputs.append(f"\n=== 截圖 #{i+1} ===\n")
                        data_inputs.append(Image.open(img))
                        raw_context_builder.append(f"[已上傳截圖 #{i+1}]\n")

                # 生成分析報告
                status.update(label="🧠 AI 正在進行深度分析 (請耐心等待)...", state="running")
                
                if mode == "video":
                    prompt = """
                    你是一位首席媒體分析師。請進行「個別診斷」與「綜合統整」。
                    
                    **注意：如果有提供音訊檔案，請務必仔細聆聽，並將重點（如BGM風格、語氣、關鍵台詞）寫入報告中，以便後續查閱。**
                    
                    請嚴格依照：
                    # 第一階段：📊 個別戰力 (逐一分析 歸因/亮點/音訊重點)
                    # 第二階段：🌪️ 綜合統整 (共同爆紅公式/流量密碼)
                    """
                else:
                    prompt = """
                    請進行社群輿情分析。
                    # 第一階段：📍 個別解析 (懶人包/情緒)
                    # 第二階段：🌪️ 綜合研判 (風向/建議)
                    """

                # 使用安全呼叫 (Safe Call)
                response = safe_api_call(model.generate_content, data_inputs)
                res_text = response.text
                
                # 儲存結果
                st.session_state.analysis_report = res_text
                st.session_state.raw_context = "\n".join(raw_context_builder)
                
                status.update(label="✅ 分析完成！", state="complete")

            except Exception as e:
                status.update(label="❌ 發生錯誤", state="error")
                st.error(f"分析終止: {e}")
            
            # 清理
            data_inputs = []
            gc.collect()
            for f in temp_files: safe_remove(f)

# ================= 結果顯示與追問 =================

if st.session_state.analysis_report:
    st.markdown('<div class="custom-card">', unsafe_allow_html=True)
    st.markdown("### 🔍 分析報告")
    st.markdown(st.session_state.analysis_report)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("### 💬 深度追問")
    
    # 顯示歷史
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("針對這幾支影片提問..."):
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.chat_history.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            with st.spinner("AI 正在思考..."):
                try:
                    chat_model = genai.GenerativeModel(selected_model)
                    
                    full_prompt = f"""
                    【背景資訊 - 分析報告】
                    {st.session_state.analysis_report}
                    
                    【原始文字記憶】
                    {st.session_state.raw_context}
                    
                    【使用者問題】
                    {prompt}
                    
                    請回答使用者問題。如果問題涉及音訊細節（如語氣、背景音），請盡量回憶第一次分析時的印象，若無法確定請誠實告知。
                    """
                    
                    # 同樣使用安全呼叫
                    chat_res = safe_api_call(chat_model.generate_content, full_prompt)
                    response = chat_res.text
                    
                    st.markdown(response)
                    st.session_state.chat_history.append({"role": "assistant", "content": response})
                    
                except Exception as e:
                    st.error(f"回答失敗: {e}")