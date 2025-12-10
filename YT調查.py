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
from io import BytesIO
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

nest_asyncio.apply()

# --- 1. 頁面設定 ---
st.set_page_config(
    page_title="TrendScope Future | 3.0 Ready",
    page_icon="🪐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. 未來感深色 UI ---
st.markdown("""
<style>
    /* 背景：深空黑 */
    .stApp { background-color: #0B0F19 !important; color: #E2E8F0 !important; }
    h1, h2, h3, h4, .stMarkdown { color: #F8FAFC !important; }
    
    /* 按鈕：霓虹紫 (Cyberpunk Style) */
    .stButton > button {
        background: linear-gradient(90deg, #7C3AED 0%, #DB2777 100%) !important;
        color: white !important;
        border: none !important;
        font-weight: 800; padding: 0.8rem; border-radius: 8px;
        text-transform: uppercase; letter-spacing: 1px;
        box-shadow: 0 0 15px rgba(124, 58, 237, 0.5);
    }
    .stButton > button:hover { box-shadow: 0 0 25px rgba(219, 39, 119, 0.7); transform: scale(1.02); }

    /* 輸入框 */
    .stTextArea textarea, .stTextInput input {
        background-color: #1E293B !important; color: #F1F5F9 !important; 
        border: 1px solid #334155 !important; border-radius: 6px;
    }
    .stTextArea textarea:focus { border-color: #DB2777 !important; }

    /* 卡片與狀態 */
    .custom-card { background-color: #111827; padding: 25px; border: 1px solid #1F2937; border-radius: 12px; margin-bottom: 25px; }
    .model-tag { background-color: #374151; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; color: #A5F3FC; }
    
    /* 思考過程區塊 */
    .thinking-box {
        background-color: #171717; border-left: 3px solid #7C3AED;
        padding: 10px; margin-bottom: 10px; font-family: monospace; font-size: 0.9em; color: #A3A3A3;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. 狀態初始化 ---
if "analysis_report" not in st.session_state: st.session_state.analysis_report = ""
if "raw_context" not in st.session_state: st.session_state.raw_context = ""
if "sorted_models" not in st.session_state: st.session_state.sorted_models = []

# --- 核心：模型版本演算法 ---
def sort_models_by_version(models):
    """
    自動排序模型，優先順序：3.0 > 2.5 > 2.0 > 1.5 > Pro > Flash
    """
    def score_model(name):
        score = 0
        if "gemini-3" in name: score += 5000
        elif "gemini-2.5" in name: score += 4000
        elif "gemini-2.0" in name: score += 3000
        elif "gemini-1.5" in name: score += 1000
        
        if "pro" in name: score += 500
        if "flash" in name: score += 300
        if "exp" in name or "preview" in name: score -= 50 # 預覽版稍微扣分(不穩)，但如果是3.0仍會排前面
        return score

    return sorted(models, key=score_model, reverse=True)

# --- Word 導出 ---
def create_word_docx(markdown_text):
    doc = Document()
    doc.add_heading('TrendScope 未來輿情報告', 0).alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"生成模型: Gemini AI | 時間: {time.strftime('%Y-%m-%d')}")
    
    for line in markdown_text.split('\n'):
        line = line.strip()
        if not line: continue
        if line.startswith('# '): doc.add_heading(line.replace('# ', ''), 1)
        elif line.startswith('## '): doc.add_heading(line.replace('## ', ''), 2)
        elif line.startswith('- '): doc.add_paragraph(line.replace('- ', ''), style='List Bullet')
        else: doc.add_paragraph(line)
        
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

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
    st.title("🪐 未來控制台")
    api_key = st.text_input("Google API Key", type="password", value=st.session_state.get("api_key", ""))
    
    if st.button("🔄 掃描最新模型 (3.0/2.5)"):
        if api_key:
            try:
                genai.configure(api_key=api_key)
                all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                # 執行智慧排序
                st.session_state.sorted_models = sort_models_by_version(all_models)
                st.session_state.api_key = api_key
                st.success(f"已鎖定最新技術：{st.session_state.sorted_models[0]}")
            except Exception as e:
                st.error(f"連線失敗: {e}")

    options = st.session_state.sorted_models if st.session_state.sorted_models else ["models/gemini-1.5-flash"]
    selected_model = st.selectbox("核心引擎", options)
    
    # 顯示模型標籤
    if "gemini-3" in selected_model:
        st.markdown('<span class="model-tag">🔥 Gemini 3.0 (Next Gen)</span>', unsafe_allow_html=True)
        st.caption("具備 Agentic 推理能力，能理解極其複雜的因果關係。")
    elif "gemini-2.5" in selected_model:
        st.markdown('<span class="model-tag">⚡ Gemini 2.5 (Current Gen)</span>', unsafe_allow_html=True)
        st.caption("Native Audio 增強，聽覺分析更敏銳。")
    
    use_thinking = st.toggle("🧠 啟用深度思考 (Chain-of-Thought)", value=True)

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
    ydl_opts = {'format': 'bestaudio[ext=m4a]/bestaudio', 'outtmpl': filename, 'quiet': True, 'noplaylist': True, 'ignoreerrors': True, 'nocheckcertificate': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        if os.path.exists(filename): return filename
        return filename.replace('.m4a', '.webm') if os.path.exists(filename.replace('.m4a', '.webm')) else None
    except: return None

def safe_api_call(func, *args, **kwargs):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if "429" in str(e):
                st.toast(f"⏳ 讓 {selected_model} 休息一下... ({attempt+1})")
                time.sleep(10 * (attempt + 1))
            else: raise e
    raise Exception("API 重試失敗")

# --- 主程式 ---
st.title("TrendScope Future | 3.0 Ready")
st.markdown('<div class="custom-card">', unsafe_allow_html=True)
tab1, tab2 = st.tabs(["📺 影音深度分析", "📸 社群輿情分析"])

urls_input = ""
imgs_input = []
txt_input = ""
mode = ""

with tab1:
    urls_input = st.text_area("YouTube / TikTok 網址", height=150, key="vid_in")
    analyze_vid_btn = st.button("🚀 啟動 3.0 引擎分析", key="btn_vid")
    if analyze_vid_btn: mode = "video"

with tab2:
    imgs_input = st.file_uploader("上傳截圖", accept_multiple_files=True, type=['png', 'jpg'])
    txt_input = st.text_area("補充說明", height=100)
    analyze_soc_btn = st.button("🚀 啟動 3.0 引擎分析", key="btn_soc")
    if analyze_soc_btn: mode = "social"

st.markdown('</div>', unsafe_allow_html=True)

# ================= 邏輯核心 =================

if (mode == "video" and urls_input) or (mode == "social" and (imgs_input or txt_input)):
    if not api_key:
        st.error("請輸入 API Key")
    else:
        st.session_state.analysis_report = ""
        st.session_state.raw_context = ""
        
        data_inputs = []
        raw_context_builder = []
        temp_files = []
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(selected_model)

        with st.status("🚀 正在初始化多模態分析...", expanded=True) as status:
            try:
                if mode == "video":
                    urls = [u.strip() for u in urls_input.split('\n') if u.strip()]
                    total = len(urls)
                    progress_bar = st.progress(0)
                    
                    for i, url in enumerate(urls):
                        status.update(label=f"📥 解析素材 {i+1}/{total}...", state="running")
                        info = get_video_full_info(url)
                        
                        if info:
                            thumb_path = None
                            if info.get('thumbnail_url'):
                                thumb_path = download_image(info['thumbnail_url'], i)
                                if thumb_path: temp_files.append(thumb_path)
                            
                            meta_str = f"【素材 #{i+1}】\n標題: {info['title']}\n頻道: {info['channel']}\n觀看數: {info['views']}\n"
                            data_inputs.append(meta_str)
                            if thumb_path: data_inputs.append(thumb_path)
                            raw_context_builder.append(meta_str)

                            # 2.5/3.0 強項：Native Audio
                            # 我們不再優先抓字幕，如果模型是新的，我們優先給它聽聲音！
                            is_native_audio_model = "gemini-2.5" in selected_model or "gemini-3" in selected_model
                            
                            transcript = None
                            # 只有在舊模型或非YT時才依賴字幕
                            if not is_native_audio_model and ("youtube" in url or "youtu.be" in url):
                                vid_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
                                if vid_match: transcript = get_yt_transcript(vid_match.group(1))
                            
                            if transcript:
                                data_inputs.append(f"素材 #{i+1} 字幕:\n{transcript[:15000]}\n")
                                raw_context_builder.append(f"素材 #{i+1} 字幕已提供\n")
                            else:
                                status.update(label=f"🎧 下載音訊 (使用 Native Audio 分析)...", state="running")
                                aud_path = download_audio(url, i)
                                if aud_path:
                                    data_inputs.append(aud_path)
                                    temp_files.append(aud_path)
                                    raw_context_builder.append(f"素材 #{i+1}: [AI 已直接聆聽音訊內容]\n")
                        
                        progress_bar.progress((i + 1) / total)
                        if i < total - 1: time.sleep(2) # 避讓 429

                else:
                    status.update(label="📸 解析視覺細節...", state="running")
                    if txt_input: data_inputs.append(f"補充: {txt_input}")
                    for i, img in enumerate(imgs_input):
                        data_inputs.append(f"\n=== 截圖 #{i+1} ===\n")
                        data_inputs.append(Image.open(img))

                # --- Prompt 設計 ---
                thinking_instruction = ""
                if use_thinking:
                    thinking_instruction = """
                    【思考程序 (Thought Process)】
                    在輸出正式報告前，請先進行一段「深度推理」：
                    1. 懷疑：這是不是倖存者偏差？
                    2. 比對：這個模式在其他地方見過嗎？
                    3. 驗證：如果去掉名人光環，這個腳本還成立嗎？
                    (請將這段思考過程標註在報告最前方)
                    """

                if mode == "video":
                    prompt = f"""
                    你現在是 {selected_model}，擁有最強的多模態理解能力。
                    請分析這些素材。{thinking_instruction}
                    
                    請嚴格依照兩階段輸出：
                    
                    # 第一階段：🔬 個別深度診斷
                    (針對每個素材，分析其：1. 心理學鉤子 2. 聽覺語氣潛台詞 3. 爆紅歸因)
                    
                    # 第二階段：🌪️ 宏觀策略與實戰
                    ## 1. 流量密碼 (The Algorithm)
                    ## 2. 實戰腳本生成 (請幫我寫一個 30 秒開頭腳本，模仿表現最好的那支)
                    ## 3. 避坑指南
                    """
                else:
                    prompt = f"""
                    你現在是 {selected_model}。請分析這些社群輿情。{thinking_instruction}
                    
                    # 第一階段：📍 細節解讀
                    # 第二階段：🌪️ 綜合策略
                    ## 1. 核心爭議點
                    ## 2. 危機處理/跟風建議
                    ## 3. 模擬文案生成 (寫一篇 Threads 廢文)
                    """

                status.update(label=f"🧠 {selected_model} 正在進行深度推理...", state="running")
                response = safe_api_call(model.generate_content, data_inputs)
                st.session_state.analysis_report = response.text
                st.session_state.raw_context = "\n".join(raw_context_builder)
                
                status.update(label="✅ 分析完成！", state="complete")

            except Exception as e:
                status.update(label="❌ 失敗", state="error")
                st.error(f"分析失敗: {e}")
            
            data_inputs = []
            gc.collect()
            for f in temp_files: safe_remove(f)

# ================= 結果與導出 =================

if st.session_state.analysis_report:
    st.markdown('<div class="custom-card">', unsafe_allow_html=True)
    st.markdown("### 🔍 深度分析報告")
    
    # 簡單呈現思考過程 (如果有的話)
    if "思考程序" in st.session_state.analysis_report or "深度推理" in st.session_state.analysis_report:
        st.markdown('<div class="thinking-box">🤖 AI 思考迴路已啟動... (詳見報告內容)</div>', unsafe_allow_html=True)
        
    st.markdown(st.session_state.analysis_report)
    st.markdown('</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([1, 4])
    with col1:
        docx_file = create_word_docx(st.session_state.analysis_report)
        st.download_button("📄 下載 Word (.docx)", docx_file, "Future_Report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    with col2:
        st.download_button("📥 下載 Markdown (.md)", st.session_state.analysis_report, "Future_Report.md")

    st.markdown("---")
    if prompt := st.chat_input("向 3.0 引擎提問..."):
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("AI 思考中..."):
                chat_model = genai.GenerativeModel(selected_model)
                full_prompt = f"【報告】{st.session_state.analysis_report}\n【原始資料】{st.session_state.raw_context}\n【問題】{prompt}"
                res = safe_api_call(chat_model.generate_content, full_prompt).text
                st.markdown(res)