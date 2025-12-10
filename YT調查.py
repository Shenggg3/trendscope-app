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

nest_asyncio.apply()

# --- 1. 頁面全域設定 ---
st.set_page_config(
    page_title="TrendScope Deep Focus",
    page_icon="🌌",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. 深沉專注 UI 設計 (Elegant Dark Mode) ---
st.markdown("""
<style>
    /* 全域背景：深鐵灰，不刺眼 */
    .stApp {
        background-color: #121212 !important;
        color: #E0E0E0 !important;
    }
    
    /* 標題與內文顏色：舒適的灰白 */
    h1, h2, h3, h4, h5, h6, .stMarkdown {
        color: #E0E0E0 !important;
    }
    p, li, label {
        color: #B0B0B0 !important;
    }
    
    /* --- 按鈕設計：沉穩的深藍色 + 白字 (高閱讀性) --- */
    .stButton > button {
        background-color: #1565C0 !important; /* 深藍色 */
        color: #FFFFFF !important; /* 純白字 */
        border: 1px solid #0D47A1 !important;
        padding: 0.8rem;
        border-radius: 6px;
        font-weight: 600 !important;
        font-size: 16px !important;
        width: 100%;
        transition: background-color 0.3s;
    }
    .stButton > button:hover {
        background-color: #1976D2 !important; /* 滑鼠經過稍微變亮 */
        border-color: #42A5F5 !important;
    }

    /* --- 輸入框：深灰底 + 灰白字 --- */
    .stTextArea textarea, .stTextInput input {
        background-color: #1E1E1E !important;
        color: #E0E0E0 !important;
        border: 1px solid #333333 !important;
        border-radius: 6px;
    }
    .stTextArea textarea:focus, .stTextInput input:focus {
        border-color: #1565C0 !important; /* 聚焦時顯示深藍框 */
        box-shadow: 0 0 0 1px #1565C0 !important;
    }

    /* --- 卡片容器：比背景稍亮的深灰 --- */
    .custom-card {
        background-color: #1E1E1E;
        padding: 25px;
        border: 1px solid #333;
        border-radius: 10px;
        margin-bottom: 25px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* --- Tabs 分頁 --- */
    .stTabs [data-baseweb="tab-list"] {
        background-color: #121212;
        gap: 5px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #2C2C2C;
        color: #AAAAAA;
        border: none;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1565C0 !important;
        color: white !important;
    }
    
    /* --- 數據指標卡 --- */
    .metric-card {
        background-color: #252525;
        border-left: 4px solid #1565C0; /* 藍色側邊條 */
        padding: 15px;
        border-radius: 8px;
        text-align: center;
    }
    .metric-val { font-size: 28px; font-weight: bold; color: #64B5F6 !important; } /* 淺藍色數字 */
    .metric-lbl { font-size: 14px; color: #BBBBBB !important; font-weight: normal; }

    /* 錯誤訊息 */
    .stAlert {
        background-color: #2C0B0E !important;
        color: #FFCDD2 !important;
        border: 1px solid #B71C1C;
    }
</style>
""", unsafe_allow_html=True)

# --- Session State ---
if "analysis_result" not in st.session_state: st.session_state.analysis_result = ""
if "available_models" not in st.session_state: st.session_state.available_models = []

# --- 核心檔案處理 (安全版) ---
def safe_remove(filepath):
    """安全刪除檔案"""
    try:
        if os.path.exists(filepath):
            gc.collect()
            time.sleep(0.5)
            os.remove(filepath)
    except: pass

def load_image_safe(filepath):
    """安全讀取圖片"""
    try:
        with Image.open(filepath) as img:
            img.load()
            return img.copy()
    except: return None

# --- 側邊欄 ---
with st.sidebar:
    st.title("🌌 控制面板")
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
                "thumbnail_url": info.get('thumbnail', None),
                "url": url
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
        'quiet': True,
        'noplaylist': True,
        'ignoreerrors': True,
        'nocheckcertificate': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        if os.path.exists(filename): return filename
        return filename.replace('.m4a', '.webm') if os.path.exists(filename.replace('.m4a', '.webm')) else None
    except: return None

def run_ai_analysis(api_key, model_name, prompt, inputs):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    payload = [prompt]
    
    for item in inputs:
        if isinstance(item, str) and os.path.exists(item):
            if item.endswith(('.m4a', '.mp3', '.webm')):
                f = genai.upload_file(item)
                retry = 0
                while f.state.name == "PROCESSING" and retry < 20: 
                    time.sleep(2); f = genai.get_file(f.name); retry += 1
                if f.state.name == "ACTIVE": payload.append(f)
            elif item.endswith(('.jpg', '.png')):
                img = load_image_safe(item)
                if img: payload.append(img)
        elif isinstance(item, Image.Image):
            payload.append(item)
        else:
            payload.append(item)
            
    try:
        return model.generate_content(payload).text
    except Exception as e:
        if "429" in str(e):
            st.toast("⏳ 請求過於頻繁，等待 10 秒後重試...", icon="⏳")
            time.sleep(10)
            return model.generate_content(payload).text
        raise e

# --- 主程式 ---
st.title("TrendScope Deep Focus | 深沉專注版")
st.markdown('<div class="custom-card">', unsafe_allow_html=True)
tab1, tab2 = st.tabs(["📺 影音綜合分析", "📸 圖文截圖分析"])

data_inputs = []
temp_files = []
source_mode = ""

with tab1:
    st.markdown("#### 🔗 輸入網址 (支援批量)")
    video_urls = st.text_area("YouTube / TikTok 網址 (一行一個)", height=150, placeholder="https://www.youtube.com/watch?v=...", key="vid_in")
    if st.button("🚀 啟動完整分析 (個別+綜合)", key="btn_vid"):
        if not api_key: st.error("請輸入 API Key")
        elif not video_urls.strip(): st.warning("請輸入網址")
        else:
            urls = [u.strip() for u in video_urls.split('\n') if u.strip()]
            source_mode = "video"
            prog = st.progress(0)
            status = st.empty()
            
            for i, url in enumerate(urls):
                status.markdown(f"**🔍 正在掃描第 {i+1} 個來源...**")
                info = get_video_full_info(url)
                if info:
                    thumb_path = None
                    if info.get('thumbnail_url'):
                        thumb_path = download_image(info['thumbnail_url'], i)
                        if thumb_path: temp_files.append(thumb_path)
                    
                    # 這裡加上明確的標記，讓 AI 知道這是第幾個素材
                    header_text = f"\n=== 【素材 #{i+1}】 ===\n標題: {info['title']}\n頻道: {info['channel']}\n觀看數: {info['views']}\n"
                    data_inputs.append(header_text)
                    if thumb_path: data_inputs.append(thumb_path)

                    is_yt = "youtube" in url or "youtu.be" in url
                    transcript = None
                    if is_yt:
                        vid_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
                        if vid_match: transcript = get_yt_transcript(vid_match.group(1))
                    
                    if transcript:
                        data_inputs.append(f"素材 #{i+1} 字幕內容:\n{transcript[:6000]}")
                    else:
                        aud_path = download_audio(url, i)
                        if aud_path:
                            data_inputs.append(aud_path)
                            temp_files.append(aud_path)
                prog.progress((i+1)/len(urls))
            status.empty()

with tab2:
    uploaded_imgs = st.file_uploader("上傳截圖", accept_multiple_files=True, type=['png', 'jpg'])
    text_context = st.text_area("補充說明", height=100)
    if st.button("🚀 啟動完整分析 (個別+綜合)", key="btn_soc"):
        if api_key and (uploaded_imgs or text_context):
            source_mode = "social"
            if text_context: data_inputs.append(f"補充: {text_context}")
            for i, img in enumerate(uploaded_imgs):
                data_inputs.append(f"\n=== 【素材 #{i+1}】 ===\n")
                data_inputs.append(Image.open(img))
            st.success(f"已載入 {len(uploaded_imgs)} 張圖")

st.markdown('</div>', unsafe_allow_html=True)

# --- 執行分析 (邏輯修改：先個別，再綜合) ---
if data_inputs:
    st.markdown("### 🔍 分析報告")
    with st.spinner("AI 正在進行：個別診斷 -> 交叉比對 -> 綜合歸納..."):
        
        # --- Prompt 重寫：強制分階段輸出 ---
        if source_mode == "video":
            prompt = f"""
            你是一位首席媒體分析師。我提供了 {len(temp_files) if temp_files else '多'} 份影片素材。
            
            請嚴格依照以下 **兩階段流程** 輸出繁體中文報告：

            # 第一階段：📊 個別戰力診斷 (請逐一分析)
            (請針對每一個素材，分別列出以下 3 點。若素材很多，請精簡重點)
            
            **📍 素材 #1 分析**
            - **標題與封面**: (吸睛點在哪？是否有名人？)
            - **流量歸因**: (是人紅還是片紅？)
            - **核心亮點**: (腳本結構或剪輯的最大優點)
            
            **📍 素材 #2 分析** ... (以此類推)

            ---
            # 第二階段：🌪️ 綜合統整與洞察 (Macro Synthesis)
            
            ## 1. 共同爆紅公式 (The Pattern)
            (綜合以上所有影片，它們有沒有**共通點**？例如：BGM 風格？開頭前 3 秒的套路？)

            ## 2. 流量密碼儀表板
            - **🔥 平均熱度指數**: (0-100)
            - **🏷️ 共同關鍵字**: (3-5個)

            ## 3. 最佳執行建議
            (如果要模仿，哪一支是最好的參考範本？為什麼？)
            """
        else:
            prompt = """
            請進行**社群輿情分析**。
            
            # 第一階段：📍 個別截圖解析
            (請針對每一張截圖/貼文進行快速診斷：它在講什麼？情緒為何？)
            
            ---
            # 第二階段：🌪️ 綜合輿情研判
            
            ## 1. 懶人包總結 (The Big Picture)
            (這些內容綜合起來，核心爭議點是什麼？)

            ## 2. 輿論風向球
            - **🔥 熱議指數**: (0-100)
            - **⚖️ 風向判定**: (支持/反對/炎上/同溫層)

            ## 3. 創作者/小編建議
            (面對這種風向，該如何操作？)
            """

        try:
            res = run_ai_analysis(api_key, selected_model, prompt, data_inputs)
            st.session_state.analysis_result = res
            
            # 顯示結果 (簡單指標 + 詳細報告)
            try:
                score = re.search(r"指數.*(\d{2,3})", res)
                s_val = score.group(1) if score else "N/A"
                c1, c2 = st.columns([1, 3])
                with c1: st.markdown(f'<div class="metric-card"><div class="metric-val">{s_val}</div><div class="metric-lbl">🔥 綜合熱度</div></div>', unsafe_allow_html=True)
            except: pass
            
            st.markdown('<div class="custom-card">', unsafe_allow_html=True)
            st.markdown(res)
            st.markdown('</div>', unsafe_allow_html=True)
            st.download_button("📥 下載完整報告", res, file_name="full_report.md")

        except Exception as e:
            st.error(f"分析中斷: {e}")
            
    # 清理
    data_inputs = [] 
    gc.collect() 
    for f in temp_files: safe_remove(f)

# --- 追問 ---
if st.session_state.analysis_result:
    st.markdown('<div class="custom-card">', unsafe_allow_html=True)
    user_q = st.text_input("💬 針對報告追問 AI...", key="chat_in")
    if st.button("送出", key="chat_btn"):
        try:
            chat_model = genai.GenerativeModel(selected_model)
            st.markdown(chat_model.generate_content(f"報告:\n{st.session_state.analysis_result}\n\n問:{user_q}").text)
        except: st.error("追問失敗")
    st.markdown('</div>', unsafe_allow_html=True)