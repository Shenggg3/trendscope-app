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
    page_title="TrendScope Master | 腳本生成版",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. 深色高對比 UI ---
st.markdown("""
<style>
    .stApp { background-color: #0F172A !important; color: #E2E8F0 !important; }
    h1, h2, h3, h4, .stMarkdown { color: #F8FAFC !important; }
    
    /* 按鈕：深海藍漸層 */
    .stButton > button {
        background: linear-gradient(135deg, #0f4c75 0%, #3282b8 100%) !important;
        color: white !important; font-weight: 800; padding: 0.8rem; border-radius: 8px;
        border: 1px solid #bbe1fa !important; letter-spacing: 1px;
    }
    .stButton > button:hover { transform: scale(1.02); box-shadow: 0 0 15px rgba(50, 130, 184, 0.6); }

    /* 輸入框 */
    .stTextArea textarea, .stTextInput input {
        background-color: #1E293B !important; color: white !important; border: 1px solid #475569 !important;
    }
    
    /* 數據儀表板 */
    .metric-card {
        background-color: #1e293b; border-left: 5px solid #3282b8;
        padding: 15px; border-radius: 8px; text-align: center; margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .metric-val { font-size: 32px; font-weight: 900; color: #3282b8; }
    .metric-lbl { font-size: 14px; color: #94a3b8; font-weight: bold; text-transform: uppercase; }

    /* 資訊卡片 */
    .info-card {
        background-color: #111827; padding: 15px; border-radius: 8px; 
        border: 1px solid #374151; margin-bottom: 10px; font-size: 0.9em;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. 狀態初始化 ---
if "analysis_report" not in st.session_state: st.session_state.analysis_report = ""
if "raw_context" not in st.session_state: st.session_state.raw_context = ""
if "sorted_models" not in st.session_state: st.session_state.sorted_models = []

# --- 核心：模型排序 ---
def sort_models_by_version(models):
    def score_model(name):
        score = 0
        if "gemini-3" in name: score += 5000
        elif "gemini-2.5" in name: score += 4000
        elif "gemini-1.5-pro" in name: score += 3000
        elif "gemini-1.5-flash" in name: score += 1000
        if "exp" in name: score -= 50
        return score
    return sorted(models, key=score_model, reverse=True)

# --- Word 導出 ---
def create_word_docx(markdown_text):
    doc = Document()
    doc.add_heading('TrendScope 分析與腳本報告', 0).alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"生成時間: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    for line in markdown_text.split('\n'):
        line = line.strip()
        if not line: continue
        if line.startswith('# '): doc.add_heading(line.replace('# ', ''), 1)
        elif line.startswith('## '): doc.add_heading(line.replace('## ', ''), 2)
        elif line.startswith('### '): doc.add_heading(line.replace('### ', ''), 3)
        elif line.startswith('- '): doc.add_paragraph(line.replace('- ', ''), style='List Bullet')
        elif line.startswith('|'): doc.add_paragraph(line, style='Intense Quote') # 表格或強調
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
    st.title("🎬 控制中心")
    api_key = st.text_input("Google API Key", type="password", value=st.session_state.get("api_key", ""))
    
    if st.button("🔄 掃描模型清單"):
        if api_key:
            try:
                genai.configure(api_key=api_key)
                all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                st.session_state.sorted_models = sort_models_by_version(all_models)
                st.session_state.api_key = api_key
                st.success(f"最佳模型：{st.session_state.sorted_models[0]}")
            except Exception as e: st.error(f"錯誤: {e}")

    options = st.session_state.sorted_models if st.session_state.sorted_models else ["models/gemini-1.5-flash"]
    selected_model = st.selectbox("核心引擎", options)
    
    st.info("💡 **腳本生成已啟用**\nAI 將自動撰寫分鏡腳本，您可以直接下載 Word 檔使用。")

# --- 工具函數 ---
def get_video_full_info(url):
    ydl_opts = {
        'quiet': True, 'noplaylist': True, 'extract_flat': True, 'skip_download': True,
        'http_headers': {'User-Agent': 'Mozilla/5.0'}
    }
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
        res = requests.get(url, stream=True, timeout=10)
        if res.status_code == 200:
            with open(filename, 'wb') as f: f.write(res.content)
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
        'format': 'bestaudio[ext=m4a]/bestaudio', 'outtmpl': filename,
        'quiet': True, 'noplaylist': True, 'ignoreerrors': True, 'nocheckcertificate': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        if os.path.exists(filename): return filename
        webm = filename.replace('.m4a', '.webm')
        if os.path.exists(webm): return webm
        return None
    except: return None

def safe_api_call(func, *args, **kwargs):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if "429" in str(e):
                time.sleep(10 * (attempt + 1))
            else: raise e
    raise Exception("API 重試失敗")

# --- 主程式 ---
st.title("TrendScope Master | 腳本生成版")
st.markdown("### 💠 影音輿情與自動化腳本系統")

tab1, tab2 = st.tabs(["📺 影音智慧分析 (YT/TikTok)", "📸 社群圖文分析"])

urls_input = ""
imgs_input = []
txt_input = ""
mode = ""
data_inputs = []
temp_files = []
raw_context_builder = []

with tab1:
    urls_input = st.text_area("輸入網址 (一行一個)", height=150, key="vid_in")
    analyze_vid_btn = st.button("🚀 啟動完整分析 + 生成腳本", key="btn_vid")
    if analyze_vid_btn: mode = "video"

with tab2:
    imgs_input = st.file_uploader("上傳截圖", accept_multiple_files=True, type=['png', 'jpg'])
    txt_input = st.text_area("補充說明", height=100)
    analyze_soc_btn = st.button("🚀 啟動完整分析 + 生成文案", key="btn_soc")
    if analyze_soc_btn: mode = "social"

# ================= 邏輯核心 =================

if (mode == "video" and urls_input) or (mode == "social" and (imgs_input or txt_input)):
    if not api_key:
        st.error("請輸入 API Key")
    else:
        st.session_state.analysis_report = ""
        st.session_state.raw_context = ""
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(selected_model)

        with st.status("🚀 正在執行深度運算...", expanded=True) as status:
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
                            
                            st.write(f"✅ 已載入: {info['title']}")
                            
                            meta_str = f"【素材 #{i+1} Metadata】\n標題: {info['title']}\n頻道: {info['channel']}\n觀看數: {info['views']}\n"
                            data_inputs.append(meta_str)
                            if thumb_path: data_inputs.append(thumb_path)
                            raw_context_builder.append(meta_str)

                            transcript = None
                            use_audio_first = "gemini-2.5" in selected_model or "gemini-3" in selected_model
                            
                            if not use_audio_first:
                                if "youtube" in url or "youtu.be" in url:
                                    vid_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
                                    if vid_match: transcript = get_yt_transcript(vid_match.group(1))

                            if transcript:
                                trans_str = f"素材 #{i+1} 字幕:\n{transcript[:10000]}\n"
                                data_inputs.append(trans_str)
                                raw_context_builder.append(trans_str)
                            else:
                                status.update(label=f"🎧 素材 {i+1}: 聽覺分析中...", state="running")
                                aud_path = download_audio(url, i)
                                if aud_path:
                                    data_inputs.append(aud_path)
                                    temp_files.append(aud_path)
                                    raw_context_builder.append(f"素材 #{i+1}: [AI 已聆聽音訊]\n")
                        
                        progress_bar.progress((i + 1) / total)
                        if i < total - 1: time.sleep(2)

                else:
                    status.update(label="📸 解析圖片...", state="running")
                    if txt_input: data_inputs.append(f"補充: {txt_input}")
                    for i, img in enumerate(imgs_input):
                        data_inputs.append(f"\n=== 截圖 #{i+1} ===\n")
                        data_inputs.append(Image.open(img))

                # --- Prompt 設計 (加入第4點腳本生成) ---
                status.update(label=f"🧠 {selected_model} 正在生成分析與腳本...", state="running")
                
                if mode == "video":
                    prompt = """
                    你是一位首席媒體分析師與腳本導演。請進行分析並產出腳本。
                    
                    請嚴格依照以下結構輸出：
                    
                    ========================================
                    PART 1: 🔬 個別深度診斷 (Individual Analysis)
                    ========================================
                    (請針對每一個素材，分別簡短分析：流量歸因(人紅/片紅)、核心亮點)

                    ========================================
                    PART 2: 🌪️ 綜合歸納統整 (Macro Synthesis)
                    ========================================
                    ## 1. 共同爆紅公式
                    ## 2. 流量儀表板 (指數/Hashtags)
                    ## 3. 最佳執行建議

                    ========================================
                    PART 3: 🔥 實戰生成：爆款腳本 (AI Script)
                    ========================================
                    請模仿這次分析中**表現最好、最值得參考**的那支影片的風格與節奏，
                    幫我寫一個 **30-60秒 短影音拍攝腳本**。主題請設定為與原影片類似的領域。
                    
                    請使用以下格式：
                    **【腳本標題】**: (吸睛的標題)
                    **【預期情緒】**: (例如：快節奏/懸疑/搞笑)
                    
                    | 時間 | 畫面/運鏡 (Visual) | 台詞/旁白 (Audio) | 備註/音效 |
                    | --- | --- | --- | --- |
                    | 0-3s | (描述開頭鉤子) | (第一句台詞) | (音效提示) |
                    | ... | ... | ... | ... |
                    """
                else:
                    prompt = """
                    請進行社群輿情分析。
                    
                    PART 1: 📍 個別截圖解讀
                    PART 2: 🌪️ 綜合輿情研判 (爭議點/風向/建議)
                    
                    PART 3: 🔥 實戰生成：爆款文案 (AI Copywriting)
                    請模仿這次最紅的貼文風格，幫我寫一篇適合發在 Threads/IG 的文案。
                    請包含：
                    - **吸睛首圖建議**
                    - **內文 (含分段與 Emoji)**
                    - **引導留言的結尾 (CTA)**
                    """

                response = safe_api_call(model.generate_content, data_inputs)
                st.session_state.analysis_report = response.text
                st.session_state.raw_context = "\n".join(raw_context_builder)
                
                status.update(label="✅ 完成！", state="complete")

            except Exception as e:
                status.update(label="❌ 失敗", state="error")
                st.error(f"分析失敗: {e}")
            
            data_inputs = []
            gc.collect()
            for f in temp_files: safe_remove(f)

# ================= 結果顯示 =================

if st.session_state.analysis_report:
    # 儀表板
    try:
        res = st.session_state.analysis_report
        score_match = re.search(r"指數.*(\d{2,3})", res)
        score = score_match.group(1) if score_match else "N/A"
        
        tag_match = re.search(r"(密碼|標籤).*[:：]\s*(.+)", res)
        tags = tag_match.group(1).split('\n')[0] if tag_match else "分析中"
        
        c1, c2 = st.columns([1, 3])
        with c1: st.markdown(f'<div class="metric-card"><div class="metric-val">{score}</div><div class="metric-lbl">🔥 綜合熱度</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card"><div class="metric-val" style="font-size:20px; color:#e2e8f0;">{tags}</div><div class="metric-lbl">🏷️ 核心關鍵字</div></div>', unsafe_allow_html=True)
    except: pass

    # 完整報告
    st.markdown('<div class="info-card">', unsafe_allow_html=True)
    st.markdown("### 📝 完整分析與腳本")
    st.markdown(st.session_state.analysis_report)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 導出
    c1, c2 = st.columns([1, 4])
    with c1:
        docx_file = create_word_docx(st.session_state.analysis_report)
        st.download_button("📄 下載 Word (含腳本)", docx_file, "Script_Report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    with c2:
        st.download_button("📥 下載 Markdown", st.session_state.analysis_report, "Report.md")

    # 追問
    st.markdown("---")
    if prompt := st.chat_input("對腳本不滿意？請 AI 修改 (例如：把開頭改得更聳動一點)..."):
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("AI 修改中..."):
                chat_model = genai.GenerativeModel(selected_model)
                full_prompt = f"【報告】{st.session_state.analysis_report}\n【原始記憶】{st.session_state.raw_context}\n【修改要求】{prompt}"
                res = safe_api_call(chat_model.generate_content, full_prompt).text
                st.markdown(res)