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
from collections import deque

nest_asyncio.apply()

# --- 1. 頁面設定 ---
st.set_page_config(
    page_title="TrendScope Monitor | 流量監控版",
    page_icon="📟",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. 深色 UI ---
st.markdown("""
<style>
    .stApp { background-color: #121212 !important; color: #E0E0E0 !important; }
    h1, h2, h3, h4, h5, h6, .stMarkdown { color: #E0E0E0 !important; }
    
    /* 按鈕 */
    .stButton > button {
        background-color: #00695C !important; color: white !important;
        border: 1px solid #4DB6AC !important; font-weight: 600;
        width: 100%; padding: 0.8rem; border-radius: 6px;
    }
    .stButton > button:hover { background-color: #00897B !important; }

    /* 輸入框 */
    .stTextArea textarea, .stTextInput input {
        background-color: #1E1E1E !important; color: #E0E0E0 !important; border: 1px solid #333 !important;
    }
    
    /* 流量監控條 */
    .rpm-box {
        background-color: #263238; border: 1px solid #37474F;
        padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px;
    }
    .rpm-val { font-size: 24px; font-weight: bold; color: #4DB6AC; }
    .rpm-label { font-size: 12px; color: #B0BEC5; }
    .progress-safe { color: #4DB6AC; }
    .progress-warn { color: #FFD54F; }
    .progress-danger { color: #EF5350; }
    
    /* 狀態顯示 */
    .stStatusWidget { background-color: #1E1E1E !important; border: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

# --- 3. 狀態與計數器初始化 ---
if "analysis_report" not in st.session_state: st.session_state.analysis_report = ""
if "raw_context" not in st.session_state: st.session_state.raw_context = ""
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "available_models" not in st.session_state: st.session_state.available_models = []

# API 請求時間戳記 (用來計算 RPM)
if "api_timestamps" not in st.session_state:
    st.session_state.api_timestamps = []

# --- 4. 流量監控邏輯 ---
def record_api_call():
    """記錄一次 API 呼叫"""
    now = time.time()
    st.session_state.api_timestamps.append(now)
    # 清理超過 60 秒的舊紀錄
    st.session_state.api_timestamps = [t for t in st.session_state.api_timestamps if now - t < 60]

def get_rpm_status():
    """計算當前 RPM (每分鐘請求數)"""
    now = time.time()
    # 即時清理
    st.session_state.api_timestamps = [t for t in st.session_state.api_timestamps if now - t < 60]
    count = len(st.session_state.api_timestamps)
    limit = 15 # Google Gemini Free Tier 限制約為 15 RPM
    
    color_class = "progress-safe"
    if count >= 10: color_class = "progress-warn"
    if count >= 14: color_class = "progress-danger"
    
    return count, limit, color_class

def safe_api_call(func, *args, **kwargs):
    """帶有計數與重試功能的 API 呼叫"""
    record_api_call() # 記錄這次呼叫
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                wait_time = 15 * (attempt + 1)
                st.toast(f"⚠️ 觸發流量限制，等待 {wait_time} 秒...", icon="⏳")
                time.sleep(wait_time)
            else:
                raise e
    raise Exception("API 重試失敗，請稍後再試。")

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

# --- 側邊欄：監控儀表板 ---
with st.sidebar:
    st.title("📟 控制與監控")
    
    # RPM 顯示器
    rpm, limit, color = get_rpm_status()
    percent = min(rpm / limit, 1.0)
    
    st.markdown(f"""
    <div class="rpm-box">
        <div class="rpm-label">API 負載監控 (RPM)</div>
        <div class="rpm-val {color}">{rpm} / {limit}</div>
        <div style="background:#333;height:5px;border-radius:3px;margin-top:5px;">
            <div style="background:{'#EF5350' if rpm>=14 else '#4DB6AC'};width:{percent*100}%;height:100%;border-radius:3px;"></div>
        </div>
        <div style="font-size:10px;color:#777;margin-top:5px;">每分鐘限制約 15 次</div>
    </div>
    """, unsafe_allow_html=True)

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
    default_ix = 0
    for i, m in enumerate(options):
        if "gemini-1.5-flash" in m and "8b" not in m: default_ix = i; break
    selected_model = st.selectbox("選擇模型", options, index=default_ix)
    
    if st.button("🗑️ 清除所有紀錄"):
        st.session_state.analysis_report = ""
        st.session_state.raw_context = ""
        st.session_state.chat_history = []
        st.experimental_rerun()

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
st.title("TrendScope Monitor | 流量監控版")
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

# ================= 邏輯核心：詳細進度條版 =================

if (mode == "video" and urls_input) or (mode == "social" and (imgs_input or txt_input)):
    if not api_key:
        st.error("請輸入 API Key")
    else:
        st.session_state.analysis_report = ""
        st.session_state.raw_context = ""
        st.session_state.chat_history = []
        
        data_inputs = []
        raw_context_builder = []
        temp_files = []
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(selected_model)

        # === 這裡使用 st.status 顯示詳細步驟 ===
        with st.status("🚀 任務初始化中...", expanded=True) as status:
            try:
                if mode == "video":
                    urls = [u.strip() for u in urls_input.split('\n') if u.strip()]
                    total_urls = len(urls)
                    
                    # 建立進度條
                    progress_bar = st.progress(0)
                    
                    for i, url in enumerate(urls):
                        status.update(label=f"🔄 正在處理第 {i+1}/{total_urls} 個影片: 準備中...", state="running")
                        
                        # 顯示目前處理的網址
                        st.write(f"正在掃描: `{url[:40]}...`")
                        
                        # 1. 下載資訊
                        status.update(label=f"📥 第 {i+1}/{total_urls} 個: 下載 Metadata...", state="running")
                        info = get_video_full_info(url)
                        
                        if info:
                            # 2. 下載縮圖
                            if info.get('thumbnail_url'):
                                thumb_path = download_image(info['thumbnail_url'], i)
                                if thumb_path: temp_files.append(thumb_path)
                            
                            meta_str = f"【素材 #{i+1} Metadata】\n標題: {info['title']}\n頻道: {info['channel']}\n觀看數: {info['views']}\n"
                            data_inputs.append(meta_str)
                            if thumb_path: data_inputs.append(thumb_path)
                            raw_context_builder.append(meta_str)

                            # 3. 處理內容
                            is_yt = "youtube" in url or "youtu.be" in url
                            transcript = None
                            
                            if is_yt:
                                status.update(label=f"📄 第 {i+1}/{total_urls} 個: 嘗試抓取字幕...", state="running")
                                vid_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
                                if vid_match: transcript = get_yt_transcript(vid_match.group(1))
                            
                            if transcript:
                                st.write("✅ 字幕獲取成功")
                                trans_str = f"素材 #{i+1} 字幕:\n{transcript[:10000]}\n"
                                data_inputs.append(trans_str)
                                raw_context_builder.append(trans_str)
                            else:
                                status.update(label=f"🎵 第 {i+1}/{total_urls} 個: 字幕失敗，轉為下載音訊...", state="running")
                                aud_path = download_audio(url, i)
                                if aud_path:
                                    st.write("✅ 音訊下載成功")
                                    data_inputs.append(aud_path)
                                    temp_files.append(aud_path)
                                    raw_context_builder.append(f"素材 #{i+1}: [含有音訊檔案，AI 已聆聽]\n")
                        
                        # 更新進度條
                        progress_bar.progress((i + 1) / total_urls)
                        
                        # 智慧限流：如果是批量處理，稍微停頓
                        if i < total_urls - 1:
                            time.sleep(2)

                else: # Social Mode
                    status.update(label="📸 正在讀取圖片...", state="running")
                    if txt_input:
                        data_inputs.append(f"補充: {txt_input}")
                        raw_context_builder.append(f"補充: {txt_input}\n")
                    for i, img in enumerate(imgs_input):
                        st.write(f"載入圖片: {img.name}")
                        data_inputs.append(f"\n=== 截圖 #{i+1} ===\n")
                        data_inputs.append(Image.open(img))
                        raw_context_builder.append(f"[已上傳截圖 #{i+1}]\n")

                # 生成分析報告
                status.update(label="🧠 所有素材準備就緒，AI 正在進行深度分析 (請稍候 10-30 秒)...", state="running")
                
                if mode == "video":
                    prompt = """
                    你是一位首席媒體分析師。請進行「個別診斷」與「綜合統整」。
                    **注意：如果有提供音訊檔案，請務必仔細聆聽，並將重點（如BGM風格、語氣、關鍵台詞）寫入報告中。**
                    
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

                # 呼叫 API (記錄 RPM)
                response = safe_api_call(model.generate_content, data_inputs)
                res_text = response.text
                
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

# ================= 結果與追問 =================

if st.session_state.analysis_report:
    st.markdown('<div class="custom-card">', unsafe_allow_html=True)
    st.markdown("### 🔍 分析報告")
    st.markdown(st.session_state.analysis_report)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("### 💬 深度追問")
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    if prompt := st.chat_input("提問..."):
        with st.chat_message("user"): st.markdown(prompt)
        st.session_state.chat_history.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            with st.spinner("AI 正在思考..."):
                try:
                    chat_model = genai.GenerativeModel(selected_model)
                    full_prompt = f"""
                    【報告】{st.session_state.analysis_report}
                    【原始記憶】{st.session_state.raw_context}
                    【問題】{prompt}
                    """
                    chat_res = safe_api_call(chat_model.generate_content, full_prompt)
                    response = chat_res.text
                    st.markdown(response)
                    st.session_state.chat_history.append({"role": "assistant", "content": response})
                except Exception as e:
                    st.error(f"回答失敗: {e}")