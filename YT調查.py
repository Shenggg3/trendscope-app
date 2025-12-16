import streamlit as st
import google.generativeai as genai
import yt_dlp
import os
import time
import pandas as pd
from PIL import Image
from io import BytesIO
from datetime import datetime
import re

# --- 1. 核心配置與風格 ---
st.set_page_config(
    page_title="AdCore 2026: UA Command Center",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2026 Cyberpunk AdTech 風格
st.markdown("""
<style>
    .stApp { background-color: #050505 !important; color: #00FF99 !important; }
    h1, h2, h3 { color: #ffffff !important; font-family: 'Roboto Mono', monospace; }
    .stSelectbox, .stTextInput, .stTextArea { color: white !important; }
    
    /* 核心按鈕 */
    .stButton > button {
        background: linear-gradient(90deg, #00C9FF 0%, #92FE9D 100%);
        color: #000000;
        font-weight: 900;
        border: none;
        padding: 12px 24px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* 分析卡片 */
    .metric-card {
        background: #111;
        border: 1px solid #333;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #00FF99;
        margin-bottom: 10px;
    }
    
    /* 警告與提示 */
    .warning-box { border-left: 5px solid #FFD700; background: #222; padding: 10px; }
    .hook-box { border-left: 5px solid #FF0055; background: #221010; padding: 10px; }
</style>
""", unsafe_allow_html=True)

# --- 2. 工具函數庫 ---

def get_gemini_model(api_key, model_name="gemini-1.5-flash"):
    """獲取 Gemini 模型實例"""
    genai.configure(api_key=api_key)
    # 針對廣告分析，我們需要較高的創造力與精準度
    generation_config = {
        "temperature": 0.8,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
    }
    return genai.GenerativeModel(model_name=model_name, generation_config=generation_config)

def download_video_segment(url, filename_prefix):
    """下載影片，針對廣告用途優化 (MP4)"""
    timestamp = int(time.time())
    filename = f"{filename_prefix}_{timestamp}.mp4"
    
    ydl_opts = {
        'outtmpl': filename,
        'format': 'best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        # 針對 Shorts/TikTok 優化 User-Agent
        'http_headers': {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)'}
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        if os.path.exists(filename):
            return filename
        return None
    except Exception as e:
        st.error(f"下載失敗 (可能因版權或地區限制): {str(e)}")
        return None

def upload_to_gemini(path, mime_type='video/mp4'):
    """上傳素材到 Gemini 暫存空間"""
    try:
        file = genai.upload_file(path, mime_type=mime_type)
        # 等待處理完成
        while file.state.name == "PROCESSING":
            time.sleep(1)
            file = genai.get_file(file.name)
        if file.state.name == "FAILED":
            raise ValueError("Gemini 處理檔案失敗")
        return file
    except Exception as e:
        st.error(f"上傳錯誤: {e}")
        return None

# --- 3. 側邊欄：戰略設定 ---
with st.sidebar:
    st.title("🛡️ 投放師戰情室")
    api_key = st.text_input("Gemini API Key", type="password")
    
    st.markdown("### 🎮 產品屬性")
    game_genre = st.selectbox("遊戲類型", 
        ["MMORPG (重度)", "SLG (策略/4X)", "Casino/Slots (博弈)", "Hypercasual (超休閒)", "Puzzle (三消/解謎)", "Idle (放置)"])
    
    target_audience = st.multiselect("目標受眾 (Bartle 心理學)", 
        ["Killers (競爭者)", "Achievers (成就者)", "Socializers (社交者)", "Explorers (探索者)"],
        default=["Achievers"])
    
    ad_goal = st.radio("當前優化目標", ["降低 CPI (吸量)", "提高 ROAS (大R)", "提高留存 (Retension)"])
    
    st.markdown("---")
    st.info("💡 2026 趨勢提示：\n真人實拍 + AI 特效混剪是目前 ROI 最高的素材形式。")

# --- 4. 主介面邏輯 ---
st.title("AdCore 2026: Game UA Engine")
st.caption(f"目標產品: {game_genre} | 優化方向: {ad_goal}")

tab_spy, tab_lab, tab_prompt = st.tabs(["🕵️ 競品拆解 (Spy)", "🧪 變體工廠 (A/B Test)", "🎨 AI 生產指令 (GenAI)"])

# ================= TAB 1: 競品拆解 (The Spy) =================
with tab_spy:
    st.markdown("### 🩸 解剖爆款素材")
    st.markdown("上傳競品的高消耗素材，AI 將反向工程其「吸量邏輯」。")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        video_url = st.text_input("輸入 YouTube/TikTok 連結")
    with col2:
        uploaded_video = st.file_uploader("或直接上傳 MP4", type=['mp4'])
    
    if st.button("🚀 執行深度屍檢 (Autopsy)", key="btn_spy"):
        if not api_key:
            st.error("請輸入 API Key！")
        else:
            status = st.status("正在進行多模態分析...", expanded=True)
            video_path = None
            
            # 處理影片來源
            if uploaded_video:
                video_path = f"temp_ad_{int(time.time())}.mp4"
                with open(video_path, "wb") as f: f.write(uploaded_video.getbuffer())
            elif video_url:
                status.write("📥 下載競品素材中...")
                video_path = download_video_segment(video_url, "competitor_ad")
            
            if video_path:
                status.write("👁️ 上傳至 Gemini 視覺中樞...")
                gemini_file = upload_to_gemini(video_path)
                
                if gemini_file:
                    status.write("🧠 正在分析黃金 3 秒與轉化邏輯...")
                    model = get_gemini_model(api_key)
                    
                    # === 2026 頂級投放師 Prompt ===
                    prompt = f"""
                    你現在是 2026 年最頂尖的手機遊戲廣告投放專家 (UA Manager)。
                    請針對這支遊戲廣告進行「逐幀拆解」。我們的目標是模仿它的高消耗邏輯。
                    
                    分析對象：{game_genre} 手遊
                    目標受眾：{target_audience}
                    
                    請輸出以下 Markdown 報告：

                    ### 1. 🎣 黃金 3 秒 (The Hook)
                    *   **視覺衝擊**: 前 3 秒畫面發生了什麼？(例如：戰力飆升、失敗懲罰、美女/帥哥、巨物恐懼)
                    *   **聽覺鉤子**: BGM 是激昂、懸疑還是 ASMR？有無 TTS 旁白？
                    *   **Hook 類型**: (例如：Gameplay Fail, Before/After, 隱藏福利, 假玩 Fake Ads)

                    ### 2. 🧠 心理學歸因 (Why it converts?)
                    *   利用了哪種人性弱點？(貪婪、色慾、恐懼、好勝心、強迫症)
                    *   這支廣告是針對 Bartle 玩家分類中的哪一類？為什麼？

                    ### 3. 🎬 結構拆解 (Timeline)
                    | 時間 | 畫面內容 (Visual) | 文案/旁白 (Copy) | 刺激點 (Trigger) |
                    |---|---|---|---|
                    | 0-3s | ... | ... | ... |
                    | 3-10s| ... | ... | ... |
                    | 10s+ | ... | ... | ... |

                    ### 4. 📉 缺點與優化機會 (Optimization)
                    *   這支廣告哪裡做得不夠好？
                    *   如果我們要抄襲這個創意，如何改得更強？(給出具體建議)

                    ### 5. 🏷️ 標籤 (Tags for Library)
                    請給出 5 個形容詞標籤 (例如：#解壓 #割草 #戰力比拼)
                    """
                    
                    response = model.generate_content([gemini_file, prompt])
                    st.session_state['spy_result'] = response.text
                    status.update(label="分析完成！", state="complete")
                    
                    # 清理檔案
                    try: os.remove(video_path) 
                    except: pass
            else:
                st.error("無法處理影片，請檢查來源。")

    if 'spy_result' in st.session_state:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.markdown(st.session_state['spy_result'])
        st.markdown('</div>', unsafe_allow_html=True)

# ================= TAB 2: 變體工廠 (Variation Lab) =================
with tab_lab:
    st.markdown("### 🧪 A/B Test 腳本生成矩陣")
    st.markdown("基於分析結果或概念，生成 3 種不同切入點的腳本 (Hook/Pain/Pleasure)。")
    
    base_concept = st.text_area("輸入核心玩法或概念 (或是貼上剛剛的分析結果)", 
                                value=st.session_state.get('spy_result', "例如：玩家扮演一個很弱的史萊姆，透過吞噬敵人進化成魔王。"),
                                height=150)
    
    col_a, col_b = st.columns(2)
    with col_a:
        script_duration = st.selectbox("廣告秒數", ["15s (TikTok/Shorts)", "30s (一般投放)", "60s (深度素材)"])
    with col_b:
        visual_style = st.selectbox("視覺風格", ["UE5 高質感 (Cinematic)", "UGC 真人實況 (Native)", "2D 動畫 (Cartoon)", "假玩/失敗向 (Fail Run)"])

    if st.button("⚡ 生成三組變體腳本", key="btn_script"):
        if not api_key:
            st.error("API Key 缺失")
        else:
            with st.spinner("正在構建高轉化腳本..."):
                model = get_gemini_model(api_key)
                prompt_lab = f"""
                你是資深廣告編劇。請根據以下概念，為 {game_genre} 遊戲撰寫 3 支完全不同的廣告腳本，用於 A/B Test。
                
                核心概念：{base_concept}
                時長限制：{script_duration}
                視覺風格：{visual_style}
                
                請產出以下三種變體：
                1.  **變體 A (Praise/Power)**: 強調爽感、數值爆炸、進化快感。
                2.  **變體 B (Pain/Fail)**: 強調失敗、智商挑戰、「只有 1% 人能過關」。
                3.  **變體 C (Native/Story)**: 像是玩家真實推薦、或是帶有劇情的轉折。

                格式要求 (請用表格)：
                **變體 X**
                | 秒數 | 畫面描述 (給美術看) | 旁白/音效 (給後製看) | 畫面文字 (Overlay) |
                |---|---|---|---|
                """
                
                res = model.generate_content(prompt_lab)
                st.session_state['script_result'] = res.text
    
    if 'script_result' in st.session_state:
        st.markdown(st.session_state['script_result'])
        st.download_button("📥 下載腳本 (TXT)", st.session_state['script_result'], "ad_scripts.txt")

# ================= TAB 3: AI 生產指令 (GenAI Prompts) =================
with tab_prompt:
    st.markdown("### 🎨 AI 素材生產線")
    st.markdown("將你的腳本轉化為 **Midjourney / Runway Gen-2 / Sora** 的標準指令。")
    
    if 'script_result' not in st.session_state:
        st.info("請先在「變體工廠」生成腳本，或在此輸入描述。")
        raw_script = st.text_area("輸入場景描述", "一個史萊姆吞噬了巨龍，發出金光")
    else:
        raw_script = st.text_area("參考腳本", st.session_state['script_result'], height=200)
    
    tool_target = st.selectbox("目標 AI 工具", ["Midjourney v6 (圖片)", "Runway Gen-3 / Sora (影片)", "Stable Diffusion (ControlNet)"])
    
    if st.button("✨ 生成 AI Prompts", key="btn_prompts"):
        if not api_key: st.error("API Key 缺失")
        else:
            with st.spinner("正在翻譯為 AI 語言..."):
                model = get_gemini_model(api_key)
                prompt_gen = f"""
                你現在是 AI Prompt Engineer。請閱讀上述腳本，提取關鍵的「視覺畫面 (Key Visuals)」。
                將這些畫面轉化為 {tool_target} 的專用提示詞 (Prompts)。
                
                要求：
                1. 英文輸出 (English Prompts)。
                2. 包含必要的參數 (如 Midjourney 的 --ar 9:16 --v 6.0)。
                3. 增加畫質與風格修飾詞 (e.g., Unreal Engine 5 render, 8k, hyper-realistic, cinematic lighting)。
                4. 針對廣告用途，畫面必須吸睛 (High contrast, dynamic composition)。
                
                輸出格式：
                **[場景 1]**
                Prompt: `......`
                
                **[場景 2]**
                Prompt: `......`
                """
                res_p = model.generate_content(raw_script + "\n" + prompt_gen)
                st.code(res_p.text, language="markdown")

# --- 頁尾 ---
st.markdown("---")
st.caption("AdCore 2026 v1.0 | Designed for High-Performance UA Teams | Powered by Google Gemini 1.5/2.0")