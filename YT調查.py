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
from datetime import datetime # 新增時間模組
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

nest_asyncio.apply()

# --- 1. 頁面設定 ---
st.set_page_config(
    page_title="TrendScope Final Perfect",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. 深色高對比 UI ---
st.markdown("""
<style>
    .stApp { background-color: #0F172A !important; color: #E2E8F0 !important; }
    h1, h2, h3, h4, .stMarkdown { color: #F8FAFC !important; }
    
    /* 按鈕：日落橘 (高強對比，提醒這是分析按鈕) */
    .stButton > button {
        background: linear-gradient(135deg, #ea580c 0%, #c2410c 100%) !important;
        color: white !important; font-weight: 800; padding: 0.8rem; border-radius: 8px;
        border: 1px solid #fdba74 !important; letter-spacing: 1px;
    }
    .stButton > button:hover { transform: scale(1.02); box-shadow: 0 0 15px rgba(234, 88, 12, 0.5); }

    /* 輸入框 */
    .stTextArea textarea, .stTextInput input {
        background-color: #1E293B !important; color: white !important; border: 1px solid #475569 !important;
    }
    
    /* 數據儀表板 */
    .metric-card {
        background-color: #1e293b; border-left: 5px solid #f97316;
        padding: 15px; border-radius: 8px; text-align: center; margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .metric-val { font-size: 32px; font-weight: 900; color: #f97316; }
    .metric-lbl { font-size: 14px; color: #cbd5e1; font-weight: bold; text-transform: uppercase; }

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
    doc.add_heading('TrendScope 深度分析報告', 0).alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"分析時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    for line in markdown_text.split('\n'):
        line = line.strip()
        if not line: continue
        if line.startswith('# '): doc.add_heading(line.replace('# ', ''), 1)
        elif line.startswith('## '): doc.add_heading(line.replace('## ', ''), 2)
        elif line.startswith('### '): doc.add_heading(line.replace('### ', ''), 3)
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
    st.title("🎯 控制中心")
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
    
    st.info(f"📅 **時間校正已啟用**\n系統時間：{datetime.now().strftime('%Y-%m-%d')}\nAI 將以此時間為基準進行分析。")

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
                "thumbnail_url": info.get('thumbnail', None),
                "upload_date": info.get('upload_date', 'Unknown') # 抓取上傳日期
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
        # 增加語言支援：繁中 -> 中文 -> 英文
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
st.title("TrendScope Final Perfect | 時間校正與深度版")
st.markdown("### 🎯 確保繁體中文輸出・確保深度分析結構")

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
                # 1. 取得當前時間字串
                current_time_str = datetime.now().strftime("%Y-%m-%d")
                
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
                            
                            # 在 Metadata 中加入上傳日期，供 AI 判斷時效性
                            meta_str = f"【素材 #{i+1} Metadata】\n標題: {info['title']}\n頻道: {info['channel']}\n觀看數: {info['views']}\n上傳日期(格式YYYYMMDD): {info.get('upload_date')}\n"
                            data_inputs.append(meta_str)
                            if thumb_path: data_inputs.append(thumb_path)
                            raw_context_builder.append(meta_str)

                            transcript = None
                            use_audio_first = "gemini-2.5" in selected_model or "gemini-3" in selected_model
                            
                            # 優先抓字幕
                            if "youtube" in url or "youtu.be" in url:
                                vid_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
                                if vid_match: transcript = get_yt_transcript(vid_match.group(1))

                            # 邏輯：有字幕用字幕，沒字幕用音訊
                            if transcript:
                                trans_str = f"素材 #{i+1} 字幕內容 (請基於此內容分析):\n{transcript[:15000]}\n"
                                data_inputs.append(trans_str)
                                raw_context_builder.append(trans_str)
                            else:
                                # 嘗試下載音訊
                                status.update(label=f"🎧 素材 {i+1}: 字幕缺失，轉為聽覺分析...", state="running")
                                aud_path = download_audio(url, i)
                                if aud_path:
                                    data_inputs.append(aud_path)
                                    temp_files.append(aud_path)
                                    raw_context_builder.append(f"素材 #{i+1}: [AI 已聆聽音訊檔案]\n")
                                else:
                                    st.warning(f"素材 {i+1} 無法取得內容 (無字幕且音訊下載失敗)，分析可能受限。")
                        
                        progress_bar.progress((i + 1) / total)
                        if i < total - 1: time.sleep(2)

                else:
                    status.update(label="📸 解析圖片...", state="running")
                    if txt_input: data_inputs.append(f"補充: {txt_input}")
                    for i, img in enumerate(imgs_input):
                        data_inputs.append(f"\n=== 截圖 #{i+1} ===\n")
                        data_inputs.append(Image.open(img))

                # --- Prompt 強制校正 ---
                status.update(label=f"🧠 {selected_model} 正在生成分析與腳本...", state="running")
                
                common_instruction = f"""
                **⚠️ 重要指令 (SYSTEM OVERRIDE):**
                1. **語言限制**: 輸出必須 **100% 使用繁體中文 (Traditional Chinese)**，禁止使用日文、簡體或英文(專有名詞除外)。
                2. **時間感知**: 今天是 **{current_time_str}**。請基於此日期判斷影片的時效性（例如：上個月的影片是過去式，不是未來式）。
                3. **拒絕敷衍**: 絕對**禁止**只輸出「這是一支影片...標題是...」這種簡單摘要。如果內容不足，請從封面圖、標題關鍵字進行深度推論。
                4. **結構強制**: 必須包含 PART 1, PART 2, PART 3。
                """

                if mode == "video":
                    prompt = f"""
                    {common_instruction}
                    
                    你是一位首席媒體分析師。請針對提供的素材進行深度分析。
                    
                    請嚴格依照以下結構輸出：
                    
                    ========================================
                    PART 1: 🔬 個別深度診斷 (Individual Analysis)
                    ========================================
                    (請針對每一個素材，分別列出：)
                    **📍 素材 #N**
                    - **內容深度解析**: (它到底在講什麼？亮點在哪？請引用字幕或畫面細節)
                    - **流量歸因**: (人紅 vs 片紅？如果是 Apple 發表會，是因為產品紅還是創作者紅？)
                    - **時效性判斷**: (這是不是舊聞？還是當下熱點？)

                    ========================================
                    PART 2: 🌪️ 綜合歸納統整 (Macro Synthesis)
                    ========================================
                    ## 1. 共同爆紅公式
                    ## 2. 流量儀表板 (指數/Hashtags)
                    ## 3. 最佳執行建議

                    ========================================
                    PART 3: 🔥 實戰生成：爆款腳本 (AI Script)
                    ========================================
                    請模仿表現最好的那支影片，幫我寫一個 **30-60秒 腳本**。
                    格式：
                    | 時間 | 畫面 | 台詞 | 音效 |
                    |---|---|---|---|
                    """
                else:
                    prompt = f"""
                    {common_instruction}
                    請進行社群輿情分析。
                    
                    PART 1: 📍 個別截圖解讀 (內容/情緒)
                    PART 2: 🌪️ 綜合輿情研判 (爭議點/風向/建議)
                    PART 3: 🔥 實戰生成：爆款文案 (模仿最紅的那篇)
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
    try:
        res = st.session_state.analysis_report
        score_match = re.search(r"指數.*(\d{2,3})", res)
        score = score_match.group(1) if score_match else "N/A"
        tag_match = re.search(r"(密碼|標籤).*[:：]\s*(.+)", res)
        tags = tag_match.group(1).split('\n')[0] if tag_match else "分析中"
        
        c1, c2 = st.columns([1, 3])
        with c1: st.markdown(f'<div class="metric-card"><div class="metric-val">{score}</div><div class="metric-lbl">🔥 綜合熱度</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card"><div class="metric-val" style="font-size:20px; color:#cbd5e1;">{tags}</div><div class="metric-lbl">🏷️ 核心關鍵字</div></div>', unsafe_allow_html=True)
    except: pass

    st.markdown('<div class="info-card">', unsafe_allow_html=True)
    st.markdown("### 📝 完整分析與腳本")
    st.markdown(st.session_state.analysis_report)
    st.markdown('</div>', unsafe_allow_html=True)
    
    c1, c2 = st.columns([1, 4])
    with c1:
        docx_file = create_word_docx(st.session_state.analysis_report)
        st.download_button("📄 下載 Word", docx_file, "Script_Report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    with c2:
        st.download_button("📥 下載 Markdown", st.session_state.analysis_report, "Report.md")

    st.markdown("---")
    if prompt := st.chat_input("對腳本不滿意？請 AI 修改..."):
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("AI 修改中..."):
                chat_model = genai.GenerativeModel(selected_model)
                full_prompt = f"【報告】{st.session_state.analysis_report}\n【原始記憶】{st.session_state.raw_context}\n【修改要求】{prompt}"
                res = safe_api_call(chat_model.generate_content, full_prompt).text
                st.markdown(res)