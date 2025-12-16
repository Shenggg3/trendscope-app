import streamlit as st
import google.generativeai as genai
import yt_dlp
import os
import time
import pandas as pd
from PIL import Image
import nest_asyncio
import gc
from io import BytesIO
from datetime import datetime

# 套用異步修正
nest_asyncio.apply()

# --- 1. 介面設定：暗黑軍事風格 ---
st.set_page_config(
    page_title="Game UA Sniper 2026",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS 優化：針對投手的高效儀表板 ---
st.markdown("""
<style>
    .stApp { background-color: #0b0f19 !important; color: #e0e6ed !important; }
    
    /* 按鈕風格：霓虹戰術風 */
    .stButton > button {
        background: linear-gradient(90deg, #00C9FF 0%, #92FE9D 100%);
        color: #000;
        font-weight: 900;
        border: none;
        border-radius: 4px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .stButton > button:hover { opacity: 0.9; transform: scale(1.02); }

    /* 區塊風格 */
    .metric-card {
        background: #161b22;
        border-left: 5px solid #00f260;
        padding: 15px;
        margin-bottom: 15px;
        border-radius: 5px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .hook-alert { color: #ffeb3b; font-weight: bold; }
    .action-item { color: #05ffa1; font-weight: bold; }
    
    h1, h2, h3 { font-family: 'Helvetica Neue', sans-serif; font-weight: 800; }
</style>
""", unsafe_allow_html=True)

# --- 2. 工具函數群 ---

def get_best_model(api_key):
    """自動選擇最強的 Gemini 模型"""
    genai.configure(api_key=api_key)
    models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    # 優先順序: 2.0 (最強) -> 1.5 Pro (穩定深度) -> 1.5 Flash (快速)
    priority = ["gemini-2.0", "gemini-1.5-pro", "gemini-1.5-flash"]
    for p in priority:
        for m in models:
            if p in m: return m
    return "models/gemini-1.5-flash"

def upload_to_gemini(path, mime_type=None):
    """上傳素材至 Gemini"""
    if not mime_type:
        if path.endswith('.mp4'): mime_type = 'video/mp4'
        elif path.endswith(('.png', '.jpg', '.jpeg')): mime_type = 'image/jpeg'
    
    file = genai.upload_file(path, mime_type=mime_type)
    bar = st.progress(0)
    status_text = st.empty()
    
    # 等待處理
    while file.state.name == "PROCESSING":
        bar.progress(50)
        status_text.text("☁️ 雲端處理中 (AI Vision)...")
        time.sleep(2)
        file = genai.get_file(file.name)
    
    bar.progress(100)
    status_text.empty()
    return file

def download_video(url, prefix):
    """下載影片 (YT/TikTok/Shorts)"""
    filename = f"{prefix}_{int(time.time())}.mp4"
    ydl_opts = {
        'outtmpl': filename,
        'format': 'best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'http_headers': {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)'}
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return filename if os.path.exists(filename) else None
    except Exception as e:
        return None

def create_docx(text, title):
    """生成 Word 需求單"""
    from docx import Document
    doc = Document()
    doc.add_heading(title, 0)
    for line in text.split('\n'):
        if line.startswith('### '): doc.add_heading(line.replace('### ', ''), 2)
        elif line.startswith('**'): doc.add_paragraph(line.replace('**', ''), style='Strong')
        else: doc.add_paragraph(line)
    bio = BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio

# --- 3. 側邊欄控制中心 ---
with st.sidebar:
    st.title("🎯 UA Sniper 2026")
    st.markdown("針對 ROI 與消耗優化的終極工具")
    
    api_key = st.text_input("Google API Key", type="password")
    
    st.divider()
    
    # 遊戲類型設定 (影響 Prompt)
    game_genre = st.selectbox(
        "🎮 目標遊戲類型",
        ["MMORPG (重度)", "SLG (策略/戰爭)", "Casino/Slots (博弈)", 
         "Match-3/Puzzle (三消/解謎)", "Hypercasual (超休閒)", "Idle (放置)", "Subculture (二次元)"]
    )
    
    target_audience = st.selectbox(
        "👥 目標受眾 (TA)",
        ["泛用戶 (Broad)", "大R (Whales)", "競品用戶", "年輕 Z 世代"]
    )

    st.info(f"當前策略模式：{game_genre} x {target_audience}")

# --- 4. 主邏輯：三大戰術模組 ---
st.title("🚀 2026 手遊素材投放實驗室")

tab_spy, tab_meme, tab_brief = st.tabs([
    "🕵️ 競品素材逆向 (Ad Spy)", 
    "🧬 迷因轉化 (Meme-to-Ad)", 
    "📝 需求單生成 (Designer Brief)"
])

# 全局變數
if "analysis_result" not in st.session_state: st.session_state.analysis_result = ""
if "video_file_name" not in st.session_state: st.session_state.video_file_name = ""

# === TAB 1: 競品逆向工程 ===
with tab_spy:
    st.markdown("### 拆解競品爆量素材：為什麼它能跑出消耗？")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        spy_url = st.text_input("貼上競品影片連結 (YT/Shorts/TikTok)")
        spy_upload = st.file_uploader("或直接上傳競品廣告 (MP4)", type=["mp4"])
    
    with col2:
        st.write(" ")
        st.write(" ")
        if st.button("🔥 開始逆向拆解", use_container_width=True):
            if not api_key:
                st.error("請輸入 API Key")
            else:
                target_file = None
                
                # 處理檔案來源
                if spy_upload:
                    target_file = f"temp_ad_{int(time.time())}.mp4"
                    with open(target_file, "wb") as f: f.write(spy_upload.getbuffer())
                elif spy_url:
                    with st.spinner("📥 下載競品素材中..."):
                        target_file = download_video(spy_url, "spy_video")
                
                if target_file:
                    try:
                        st.session_state.video_file_name = target_file # 存起來給 Brief 用
                        model_name = get_best_model(api_key)
                        model = genai.GenerativeModel(model_name)
                        
                        with st.spinner(f"🤖 {model_name} 正在進行逐幀分析 (Visual Breakdown)..."):
                            video_file = upload_to_gemini(target_file)
                            
                            # === 極致優化的 UA 專用 Prompt ===
                            prompt = f"""
                            你現在是 2025 年頂尖的手機遊戲 UA 優化師。你的 KPI 是 IPM (Installs Per Mille) 和 ROAS。
                            
                            請分析這支【{game_genre}】類型的遊戲廣告素材。
                            忽略無關細節，專注於「為什麼這支廣告能賺錢」。

                            請輸出以下【深度分析報告】：

                            ### 1. 🎣 黃金前 3 秒 (The Hook)
                            *   **視覺衝擊**: 第一個畫面是什麼？(例如：巨量金幣掉落、Lv.1 vs Lv.99、誇張失敗)
                            *   **心理鉤子**: 觸發了什麼人性弱點？(貪婪、好勝、強迫症、色慾、恐懼)
                            *   **停留率預估**: 為什麼手指會停下來？

                            ### 2. 🕹️ 核心展示邏輯 (The Body)
                            *   **玩法真偽**: 這是真實 Gameplay 還是 Fake Ads (素材黨)？或者是 CGI 動畫？
                            *   **爽感/痛點機制**: 影片如何展示「變強的快感」或「失敗的挫折感」？
                            *   **節奏分析**: 剪輯節奏是快是慢？BGM 如何配合？

                            ### 3. 📢 轉化引導 (The CTA)
                            *   **End Card 設計**: 結尾畫面有什麼？(Download Now 按鈕、選人畫面、裝備展示)
                            *   **文案誘因**: 使用了什麼誘導詞？(例如："只有 1% 的人能過關", "登入送 777 抽")

                            ### 4. 💡 A/B Test 延伸策略 (Action Plan)
                            *   **如果我要抄這支廣告，但我想要優化它，請給我 3 個 A/B 測試方向**：
                                1. (變更開頭): ...
                                2. (變更角色/美術): ...
                                3. (變更文案): ...
                            """
                            
                            response = model.generate_content([video_file, prompt])
                            st.session_state.analysis_result = response.text
                            st.success("✅ 逆向完成！請查看下方報告。")
                            
                    except Exception as e:
                        st.error(f"分析失敗: {e}")

    if st.session_state.analysis_result:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.markdown(st.session_state.analysis_result)
        st.markdown('</div>', unsafe_allow_html=True)

# === TAB 2: 迷因轉化 (Meme-to-Ad) ===
with tab_meme:
    st.markdown("### 蹭熱點能力：將網路迷因 (Meme) 轉化為高點擊素材")
    st.info("💡 邏輯：上傳一個搞笑/熱門影片，AI 會教你如何把它「魔改」成你的遊戲廣告。")
    
    meme_file = st.file_uploader("上傳迷因影片/GIF", type=["mp4", "gif", "mov"])
    
    if meme_file and st.button("🧬 進行基因轉殖 (Generate Concept)"):
        if not api_key:
            st.error("API Key Missing")
        else:
            tpath = f"temp_meme_{int(time.time())}.mp4"
            with open(tpath, "wb") as f: f.write(meme_file.getbuffer())
            
            model = genai.GenerativeModel(get_best_model(api_key))
            vfile = upload_to_gemini(tpath)
            
            # === 創意魔改 Prompt ===
            meme_prompt = f"""
            你是一個腦洞大開的創意總監。
            目前目標遊戲類型：【{game_genre}】。
            目標受眾：【{target_audience}】。

            畫面中是一個熱門迷因或影片。請告訴我，**如何把這個迷因梗，改編成我們遊戲的廣告？**

            請提供 2 種不同方向的劇本：

            **方案 A：直接移植 (真人實拍/UGC 風格)**
            *   演員要做什麼動作？
            *   如何在最後一刻神轉折帶入遊戲畫面？
            *   文案要怎麼寫才好笑？

            **方案 B：遊戲內重現 (In-Game Engine)**
            *   如何用遊戲的角色/3D模型來重演這個迷因？
            *   需要配合什麼樣的遊戲數值或 UI 介面？
            
            **預估成效**: 為什麼這個梗對 {target_audience} 會有效？
            """
            
            with st.spinner("🧬 正在提取迷因 DNA 並注入遊戲..."):
                res = model.generate_content([vfile, meme_prompt])
                st.markdown(res.text)

# === TAB 3: 需求單生成 (Designer Brief) ===
with tab_brief:
    st.markdown("### 📝 生產力工具：一鍵生成給美術的 Spec (規格書)")
    st.write("將目前的分析結果，轉化為標準化的表格，讓美術無法拒絕。")
    
    if not st.session_state.analysis_result:
        st.warning("⚠️ 請先在「競品素材逆向」分頁進行分析，才能生成需求單。")
    else:
        c1, c2 = st.columns(2)
        with c1:
            req_duration = st.selectbox("需求秒數", ["15s", "30s", "45s"])
            req_format = st.selectbox("尺寸", ["9:16 (直式/TikTok)", "16:9 (橫式/YT)", "1:1 (FB/IG)"])
        with c2:
            req_deadline = st.date_input("Deadline", datetime.now())
        
        if st.button("📄 產出美術需求單 (Creative Brief)"):
            brief_model = genai.GenerativeModel(get_best_model(api_key))
            
            brief_prompt = f"""
            請根據之前的分析報告，撰寫一份**給 2D/3D 美術設計師的詳細製作需求單 (Creative Brief)**。
            
            **格式要求**：
            請使用 Markdown 表格。
            
            **內容包含**：
            1. **基本資訊**: 尺寸 {req_format}, 長度 {req_duration}, 截稿日 {req_deadline}
            2. **核心概念 (One-Liner)**: 一句話講完這支影片要幹嘛。
            3. **分鏡表 (Storyboard Table)**: 
               - Columns: [時間碼, 畫面描述(Visual), 文案/旁白(Audio/Copy), 參考備註]
               - 必須詳細描述 UI 數字變化、特效 (VFX) 與動作。
            4. **素材資產需求**: 需要用到哪些角色模組、場景或 BGM。
            
            參考的分析資料如下：
            {st.session_state.analysis_result}
            """
            
            with st.spinner("✍️ 撰寫需求單中..."):
                brief_res = brief_model.generate_content(brief_prompt)
                st.markdown(brief_res.text)
                
                # 下載功能
                b_docx = create_docx(brief_res.text, f"Creative_Brief_{game_genre}_{datetime.now().date()}")
                st.download_button(
                    label="📥 下載 Word 需求單",
                    data=b_docx,
                    file_name=f"Brief_{int(time.time())}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )

# --- 5. 底部清理 ---
# 自動清理暫存檔以釋放空間
try:
    if st.session_state.video_file_name and os.path.exists(st.session_state.video_file_name):
        # 這裡不立即刪除，以免使用者還要在其他 Tab 使用，實際佈署可配合 CronJob 清理
        pass 
except: pass