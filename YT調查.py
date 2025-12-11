import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
import yt_dlp
import os
import re
import time
import requests
from PIL import Image
import nest_asyncio
import gc
from io import BytesIO
from datetime import datetime, timedelta
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH 

nest_asyncio.apply()

# --- 1. 頁面設定 ---
st.set_page_config(
    page_title="TrendScope: Deep Core",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. UI 風格 ---
st.markdown("""
<style>
    .stApp { background-color: #0F172A !important; color: #E2E8F0 !important; }
    h1, h2, h3, h4, .stMarkdown { color: #F8FAFC !important; }
    
    .btn-yt > button { background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%) !important; color: white !important; border: none; width: 100%; margin-top: 10px; }
    .btn-tiktok > button { background: linear-gradient(135deg, #06b6d4 0%, #0891b2 100%) !important; color: white !important; border: none; width: 100%; margin-top: 10px; }
    .btn-social > button { background: linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%) !important; color: white !important; border: none; width: 100%; margin-top: 10px; }
    
    .stButton > button { border-radius: 8px; font-weight: bold; }
    .info-card { background-color: #111827; padding: 20px; border-radius: 12px; border: 1px solid #374151; margin-bottom: 20px; }
    .script-studio { border-left: 4px solid #f97316; padding-left: 15px; }
    .yt-box { border-left: 4px solid #ef4444; background: #1e293b; padding: 10px; border-radius: 4px; margin-bottom: 10px;}
    .tt-box { border-left: 4px solid #06b6d4; background: #1e293b; padding: 10px; border-radius: 4px; margin-bottom: 10px;}
</style>
""", unsafe_allow_html=True)

# --- 3. 狀態初始化 ---
if "analysis_report" not in st.session_state: st.session_state.analysis_report = ""
if "raw_context" not in st.session_state: st.session_state.raw_context = ""
if "sorted_models" not in st.session_state: st.session_state.sorted_models = []
if "gemini_files_list" not in st.session_state: st.session_state.gemini_files_list = [] 
if "social_images_list" not in st.session_state: st.session_state.social_images_list = [] 
if "generated_script" not in st.session_state: st.session_state.generated_script = ""

# --- 4. 智慧 API 呼叫 ---
def smart_api_call(func, *args, **kwargs):
    max_retries = 3
    base_wait = 5
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if "429" in str(e) or "503" in str(e):
                wait_time = base_wait * (2 ** attempt)
                st.toast(f"API 冷卻中... {wait_time}秒", icon="⏳")
                time.sleep(wait_time)
            else:
                raise e
    raise Exception("API 重試失敗")

# --- 核心：模型排序 ---
def sort_models_by_version(models):
    def score_model(name):
        score = 0
        if "gemini-1.5-flash" in name: score += 10000 
        elif "gemini-2.0" in name: score += 5000 
        elif "gemini-1.5-pro" in name: score += 1000
        return score
    valid_models = [m for m in models if "gemini" in m]
    return sorted(valid_models, key=score_model, reverse=True)

# --- Word 導出 ---
def create_word_docx(text, title="分析報告"):
    doc = Document()
    doc.add_heading(f'TrendScope {title}', 0).alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    for line in text.split('\n'):
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

def safe_remove(filepath):
    try:
        if os.path.exists(filepath):
            gc.collect()
            time.sleep(0.5)
            os.remove(filepath)
    except: pass

# --- 側邊欄 ---
with st.sidebar:
    st.title("🧠 深度控制中心")
    api_key = st.text_input("Google API Key", type="password", value=st.session_state.get("api_key", ""))
    
    if st.button("🔄 連結 Google Brain"):
        if api_key:
            try:
                genai.configure(api_key=api_key)
                all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                st.session_state.sorted_models = sort_models_by_version(all_models)
                st.session_state.api_key = api_key
                st.success(f"已連接：{st.session_state.sorted_models[0]}")
            except Exception as e: st.error(f"錯誤: {e}")

    options = st.session_state.sorted_models if st.session_state.sorted_models else ["models/gemini-1.5-flash"]
    selected_model = st.selectbox("核心引擎", options)
    
    token_saver_mode = st.toggle("🍃 Token 節約模式 (YT)", value=True)
    st.markdown("---")
    st.caption("✅ 深度分析 Prompt (Deep Dive) 已恢復")

# --- 工具函數 ---
def format_timestamp(seconds):
    return str(timedelta(seconds=int(seconds)))

def calculate_days_ago(upload_date_str):
    try:
        if not upload_date_str: return "未知"
        upload_dt = datetime.strptime(upload_date_str, "%Y%m%d")
        now = datetime.now()
        diff = now - upload_dt
        days = diff.days
        if days < 0: return "未來"
        if days == 0: return "今天"
        return f"{days} 天前"
    except: return upload_date_str

def upload_to_gemini(path, mime_type=None):
    try:
        if not mime_type:
            if path.endswith('.mp4'): mime_type = 'video/mp4'
            elif path.endswith('.mp3'): mime_type = 'audio/mp3'
            elif path.endswith('.m4a'): mime_type = 'audio/mp4'
        file = genai.upload_file(path, mime_type=mime_type)
        timeout = 120 
        while file.state.name == "PROCESSING" and timeout > 0:
            time.sleep(1)
            timeout -= 1
            file = genai.get_file(file.name)
        if file.state.name == "FAILED": return None
        return file
    except Exception as e: return None

def get_yt_transcript(video_id):
    try:
        t = YouTubeTranscriptApi.get_transcript(video_id, languages=['zh-TW', 'zh', 'en'])
        return "\n".join([f"[{format_timestamp(x['start'])}] {x['text']}" for x in t])
    except: return None

def get_yt_info(url):
    ydl_opts = {'quiet': True, 'noplaylist': True, 'extract_flat': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except: return None

def get_video_comments(url, max_comments=30):
    ydl_opts = {'quiet': True, 'noplaylist': True, 'extract_flat': False, 'getcomments': True, 'skip_download': True}
    comments_text = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            comments = info.get('comments', [])
            if not comments: return "無留言"
            sorted_comments = sorted(comments, key=lambda x: x.get('like_count', 0), reverse=True)
            for i, c in enumerate(sorted_comments[:max_comments]):
                text = c.get('text', '')
                if text: comments_text.append(f"👤 {c.get('author', 'User')}: {text}")
        return "\n".join(comments_text)
    except: return "留言讀取受限"

def download_yt_audio(url, idx):
    filename = f"yt_audio_{idx}_{int(time.time())}"
    ydl_opts = {'format': 'bestaudio[ext=m4a]/bestaudio', 'outtmpl': filename + '.%(ext)s', 'quiet': True, 'ignoreerrors': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        for ext in ['m4a', 'webm', 'mp3']:
             if os.path.exists(f"{filename}.{ext}"): return f"{filename}.{ext}"
        return None
    except: return None

def download_tiktok_video(url, idx):
    filename = f"tt_video_{idx}_{int(time.time())}.mp4"
    ydl_opts = {
        'outtmpl': filename, 'format': 'best[ext=mp4]/best', 'quiet': True, 'ignoreerrors': True,
        'http_headers': {'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K)', 'Referer': 'https://www.tiktok.com/'}
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        if os.path.exists(filename): return filename
        return None
    except: return None

# === 安全模型初始化 ===
def get_model_with_fallback(model_name, use_search=False):
    if not use_search: return genai.GenerativeModel(model_name)
    try:
        return genai.GenerativeModel(model_name, tools=[{'google_search': {}}])
    except:
        st.toast("⚠️ Search Tool 初始化失敗，已切換為標準模式。", icon="🔧")
        return genai.GenerativeModel(model_name)

# ================= 主程式介面 =================
st.title("TrendScope Pro | 深度回歸版")
st.markdown("### 🔴 YT 深度結構 | 🔵 TikTok 視覺分析 | 📸 社群搜查")

tab_yt, tab_tt, tab_soc = st.tabs(["🔴 YouTube", "🔵 TikTok/Shorts", "📸 Threads/IG 圖文"])

mode = ""
data_inputs = []
raw_context_builder = []
temp_files = []

# ================= TAB 1: YouTube =================
with tab_yt:
    c1, c2 = st.columns([1, 3])
    with c1: num_yt = st.number_input("YT 數量", 1, 10, 1)
    yt_urls = []
    for i in range(num_yt):
        st.markdown(f'<div class="yt-box">', unsafe_allow_html=True)
        u = st.text_input(f"YouTube #{i+1}", key=f"yt_{i}")
        if u: yt_urls.append(u)
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('<div class="btn-yt">', unsafe_allow_html=True)
    if st.button("🚀 執行 YouTube 深度分析", key="btn_run_yt"): mode = "youtube"
    st.markdown('</div>', unsafe_allow_html=True)

# ================= TAB 2: TikTok =================
with tab_tt:
    col1, col2 = st.columns(2)
    tiktok_files_map = [] 
    with col1:
        num_tt = st.number_input("TikTok 數量", 0, 10, 1, key="tt_num")
        for i in range(num_tt):
            st.markdown(f'<div class="tt-box">', unsafe_allow_html=True)
            u = st.text_input(f"TikTok 連結 #{i+1}", key=f"tt_{i}")
            if u: tiktok_files_map.append(('url', u))
            st.markdown('</div>', unsafe_allow_html=True)
    with col2:
        uploaded_files = st.file_uploader("直接上傳 MP4", accept_multiple_files=True, type=['mp4'])
        for f in uploaded_files: tiktok_files_map.append(('file', f))
    st.markdown('<div class="btn-tiktok">', unsafe_allow_html=True)
    if st.button("👁️ 執行 TikTok 視覺分析", key="btn_run_tt"): mode = "tiktok"
    st.markdown('</div>', unsafe_allow_html=True)

# ================= TAB 3: 社群圖文 =================
with tab_soc:
    st.info("💡 **搜查功能已啟用**：支援圖片人物/地點辨識 (Google Search)。")
    imgs_input = st.file_uploader("上傳 Threads/IG 截圖", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    txt_input = st.text_area("補充說明", height=100)
    st.markdown('<div class="btn-social">', unsafe_allow_html=True)
    if st.button("📸 執行圖文搜查", key="btn_run_soc"): mode = "social"
    st.markdown('</div>', unsafe_allow_html=True)

# ================= 執行邏輯 =================
if mode:
    if not api_key:
        st.error("請輸入 API Key")
    else:
        st.session_state.analysis_report = ""
        st.session_state.raw_context = ""
        st.session_state.gemini_files_list = []
        st.session_state.social_images_list = [] 
        st.session_state.generated_script = ""
        
        genai.configure(api_key=api_key)
        
        use_search_in_analysis = (mode == "social")
        model = get_model_with_fallback(selected_model, use_search=use_search_in_analysis)

        with st.status("🚀 正在執行深度運算...", expanded=True) as status:
            try:
                # --- YouTube (Prompt 大升級) ---
                if mode == "youtube":
                    urls = [u for u in yt_urls if u.strip()]
                    total = len(urls)
                    for i, url in enumerate(urls):
                        status.update(label=f"🔴 深度分析 YT #{i+1}...", state="running")
                        info = get_yt_info(url)
                        title = info['title'] if info else "Unknown"
                        
                        meta_str = f"\n=== YT #{i+1}: {title} ===\n"
                        data_inputs.append(meta_str)
                        raw_context_builder.append(meta_str)
                        
                        comments = get_video_comments(url)
                        data_inputs.append(f"【YT #{i+1} 留言輿情】\n{comments}")
                        raw_context_builder.append(f"留言摘要:\n{comments[:500]}...\n")

                        transcript = None
                        if "v=" in url or "youtu.be" in url:
                            vid_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
                            if vid_match: transcript = get_yt_transcript(vid_match.group(1))
                        
                        use_audio = True
                        if transcript:
                            trans_str = f"【YT #{i+1} 字幕內容(含時間碼)】:\n{transcript[:35000]}"
                            data_inputs.append(trans_str)
                            raw_context_builder.append(trans_str + "\n")
                            if token_saver_mode: use_audio = False

                        if use_audio:
                            status.update(label=f"🎧 下載音訊 #{i+1} (無字幕)...", state="running")
                            aud_path = download_yt_audio(url, i)
                            if aud_path:
                                g_file = upload_to_gemini(aud_path)
                                if g_file:
                                    data_inputs.append(g_file)
                                    st.session_state.gemini_files_list.append(g_file)
                                    temp_files.append(aud_path)
                                    raw_context_builder.append(f"[音訊掛載: {g_file.name}]")
                    
                    # === 恢復您最愛的深度 Prompt ===
                    prompt = f"""
                    **⚠️ 首席流量分析師指令 (SYSTEM OVERRIDE):**
                    你現在是 YouTube 演算法與內容策略專家。請針對上述素材進行「深度拆解」。
                    我們不要淺層摘要，我們要的是「為什麼會紅」的底層邏輯。

                    請產出【TrendScope 深度結構報告】：

                    ========================================
                    PART 1: 🔬 個別深度診斷 (Deep Dive)
                    ========================================
                    (請針對每一支影片，結合 Metadata、字幕內容與網友留言進行分析)
                    **📍 影片 #N - [標題]**
                    - **內容核心與鉤子 (Hook)**: 前 15 秒到底做了什麼留住觀眾？(請引用畫面或台詞)
                    - **流量歸因**: 是標題黨？還是內容乾貨？還是情緒共鳴？
                    - **🗣️ 輿情真實風向**: 網友留言都在討論什麼？(支持/反對/玩梗/抓錯)
                    - **⏱️ 高光時刻 (Highlights)**: 請列出 2-3 個最精彩的時間點 [MM:SS] 及其內容。

                    ========================================
                    PART 2: 🌪️ 流量密碼交叉比對 (Macro Analysis)
                    ========================================
                    ### 1. 📊 綜合比較矩陣
                    | 影片標題 | 封面/選題策略 | 敘事節奏 | 觀眾情緒 | 爆紅指數 (1-5⭐) |

                    ### 2. 🧠 共同爆款公式
                    *   **選題邏輯**: 這些影片切中了什麼共同的人性弱點或需求？
                    *   **結構共性**: 它們是否都用了類似的開場或結尾？

                    ========================================
                    PART 3: 💡 最佳執行建議 (Actionable Advice)
                    ========================================
                    若我要製作一支超越這些競品的影片，我應該：
                    1. (具體建議)
                    2. (具體建議)
                    """

                # --- TikTok ---
                elif mode == "tiktok":
                    total = len(tiktok_files_map)
                    for i, (src_type, src_content) in enumerate(tiktok_files_map):
                        status.update(label=f"🔵 分析 TikTok #{i+1}...", state="running")
                        video_path = None
                        if src_type == 'url':
                            video_path = download_tiktok_video(src_content, i)
                            if not video_path: 
                                st.error(f"❌ #{i+1} 下載失敗，請改用上傳。")
                                continue
                            temp_files.append(video_path)
                        elif src_type == 'file':
                            video_path = f"upload_{i}_{int(time.time())}.mp4"
                            with open(video_path, "wb") as f: f.write(src_content.getbuffer())
                            temp_files.append(video_path)

                        if video_path:
                            status.update(label=f"👁️ 上傳影片 #{i+1}...", state="running")
                            g_file = upload_to_gemini(video_path, mime_type='video/mp4')
                            if g_file:
                                data_inputs.append(f"【TikTok #{i+1}】(請觀看影片自訂標題)")
                                data_inputs.append(g_file)
                                st.session_state.gemini_files_list.append(g_file)
                                raw_context_builder.append(f"\n=== TikTok #{i+1} ===\n[影片掛載: {g_file.name}]")
                    prompt = """
                    **TikTok 視覺分析指令:**
                    請「觀看」上述影片並進行歸納。**請根據內容自動擬定標題**。
                    PART 1: 👁️ 視覺矩陣 (AI Title | Visual Hook | BGM | Viral Factor)
                    PART 2: ⚡ 短影音流量公式 (前3秒重點 / 節奏 / 引導)
                    """

                # --- Social ---
                elif mode == "social":
                    if txt_input: data_inputs.append(f"補充: {txt_input}")
                    for i, img in enumerate(imgs_input):
                        pil_img = Image.open(img)
                        data_inputs.append(f"\n=== 圖片 #{i+1} ===\n")
                        data_inputs.append(pil_img)
                        st.session_state.social_images_list.append(pil_img)
                    
                    prompt = """
                    **社群圖文分析:**
                    請分析圖片的視覺重點與潛在情緒。
                    **注意**：我已啟用 Google Search，若有必要請隨時查詢網路資訊。
                    """

                # --- Generate ---
                if data_inputs:
                    status.update(label="🧠 AI 思考中...", state="running")
                    response = smart_api_call(model.generate_content, data_inputs + [prompt])
                    st.session_state.analysis_report = response.text
                    status.update(label="✅ 完成！", state="complete")
                else:
                    st.error("無有效素材。")

            except Exception as e: st.error(f"錯誤: {e}")
            for f in temp_files: safe_remove(f)

# ================= 結果區 =================
if st.session_state.analysis_report:
    st.markdown('<div class="info-card">', unsafe_allow_html=True)
    st.markdown("### 📊 分析報告")
    st.markdown(st.session_state.analysis_report)
    st.markdown('</div>', unsafe_allow_html=True)
    
    docx = create_word_docx(st.session_state.analysis_report, "分析報告")
    st.download_button("📥 下載報告", docx, "Report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    # === 腳本工坊 (摺疊版) ===
    st.markdown("---")
    with st.expander("🎬 腳本生成工坊 (點擊展開設定)", expanded=False):
        st.markdown('<div class="script-studio">', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        with c1:
            n_actors = st.number_input("人數", 1, 5, 1)
            s_duration = st.selectbox("長度", ["30秒", "60秒", "3分鐘"])
            s_style = st.selectbox("風格", ["幽默", "專業", "Vlog", "戲劇", "爭議"])
        
        actors_info = []
        st.markdown("#### 🎭 角色設定")
        cols = st.columns(n_actors)
        for i in range(n_actors):
            with cols[i]:
                name = st.text_input(f"名字", value=f"A{i}", key=f"nm_{i}")
                gender = st.selectbox(f"性別", ["男", "女"], key=f"gd_{i}")
                persona = st.text_input(f"人設", placeholder="例: 毒舌", key=f"ps_{i}")
                actors_info.append(f"- {name} ({gender}): {persona}")

        if st.button("✨ 生成客製化腳本"):
            with st.spinner("撰寫中..."):
                s_model = get_model_with_fallback(selected_model, use_search=False)
                s_prompt = f"""
                **專業編劇指令:**
                參考報告，寫一個 {s_duration} 的 {s_style} 腳本。
                角色：{chr(10).join(actors_info)}
                格式：Markdown 表格
                """
                res = smart_api_call(s_model.generate_content, f"報告:\n{st.session_state.analysis_report}\n指令:\n{s_prompt}")
                st.session_state.generated_script = res.text
        st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.generated_script:
        st.markdown(st.session_state.generated_script)
        s_docx = create_word_docx(st.session_state.generated_script, "腳本")
        st.download_button("📥 下載腳本", s_docx, "Script.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    # === Chat (支援搜查與回放) ===
    st.markdown("---")
    if prompt := st.chat_input("對分析有疑問？或輸入「這照片裡是誰？」"):
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("思考/搜尋中..."):
                chat_model = get_model_with_fallback(selected_model, use_search=True)
                
                chat_inputs = []
                
                # 放入所有媒體檔案 (YT/TikTok)
                if st.session_state.gemini_files_list:
                    for i, f in enumerate(st.session_state.gemini_files_list):
                        chat_inputs.append(f"【媒體 #{i+1}】")
                        chat_inputs.append(f)
                
                # 放入所有社群圖片 (Social)
                if st.session_state.social_images_list:
                    for i, img in enumerate(st.session_state.social_images_list):
                        chat_inputs.append(f"【圖片 #{i+1}】")
                        chat_inputs.append(img)
                
                chat_inputs.append(f"【報告】\n{st.session_state.analysis_report}")
                chat_inputs.append(f"【問題】{prompt}")
                chat_inputs.append("若使用者詢問人物身分或地點，請務必使用 Google Search 查詢並提供 Wiki 或新聞連結。")
                
                res = smart_api_call(chat_model.generate_content, chat_inputs).text
                st.markdown(res)