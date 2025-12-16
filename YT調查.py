import streamlit as st
import google.generativeai as genai
import time
import os
import shutil
from PIL import Image
from datetime import datetime
from io import BytesIO

# --- 1. 頁面全屏與專業風格設定 ---
st.set_page_config(
    page_title="GameAd Architect 2026 | 爆量素材實驗室",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 注入駭客級投手儀表板 CSS
st.markdown("""
<style>
    .stApp { background-color: #0b0f19 !important; color: #e0e6ed !important; }
    h1, h2, h3 { color: #00e5ff !important; font-family: 'Roboto Mono', monospace; }
    .stButton>button { 
        background: linear-gradient(90deg, #00c6ff 0%, #0072ff 100%); 
        color: white; border: none; font-weight: bold; padding: 10px 20px;
        box-shadow: 0 0 15px rgba(0, 198, 255, 0.5);
    }
    .metric-card {
        background: #16213e; border-left: 4px solid #00e5ff; padding: 15px; margin: 10px 0; border-radius: 5px;
    }
    .hook-alert { color: #ff0055; font-weight: bold; }
    .success-green { color: #00ff9d; font-weight: bold; }
    div[data-testid="stExpander"] details summary { color: #00e5ff; }
</style>
""", unsafe_allow_html=True)

# --- 2. 核心功能函數 ---

def init_gemini(api_key):
    if not api_key: return None
    genai.configure(api_key=api_key)
    # 使用具備頂尖視覺理解能力的 Pro 模型
    return genai.GenerativeModel("gemini-1.5-pro")

def upload_video_to_gemini(video_path):
    """上傳影片並等待處理完成"""
    video_file = genai.upload_file(video_path, mime_type="video/mp4")
    
    # 等待處理 (Polling)
    bar = st.progress(0)
    status_text = st.empty()
    
    wait_time = 0
    while video_file.state.name == "PROCESSING":
        status_text.text(f"📡 AI 視覺神經網路解析中... ({wait_time}s)")
        bar.progress(min(wait_time * 2, 95))
        time.sleep(2)
        wait_time += 2
        video_file = genai.get_file(video_file.name)
        
    if video_file.state.name == "FAILED":
        st.error("❌ 影片解析失敗，請確認格式。")
        return None
    
    bar.progress(100)
    status_text.empty()
    return video_file

# --- 3. 側邊欄控制中心 ---
with st.sidebar:
    st.title("⚡ 2026 UA Command Center")
    st.markdown("專為遊戲廣告優化師打造")
    
    api_key = st.text_input("輸入 Google API Key", type="password")
    
    st.markdown("---")
    st.success("🟢 系統狀態: 正常運作")
    st.info("💡 核心邏輯: Spend > Click > Install")
    
    with st.expander("🛠️ 使用說明"):
        st.write("""
        1. **素材法醫**: 上傳競品或自家跑量影片，分析為什麼紅。
        2. **裂變工廠**: 針對一支影片生成 5 種翻拍/優化方案。
        3. **設計師工單**: 生成精確的 Motion Guide。
        """)

# --- 4. 主程式邏輯 ---
st.title("🚀 GameAd Architect: 爆量素材逆向工程")
st.markdown("#### \"Decode the Winning Creative. Scale the Budget.\"")

# 初始化 Session
if "analysis_result" not in st.session_state: st.session_state.analysis_result = ""
if "video_file_ref" not in st.session_state: st.session_state.video_file_ref = None

# 分頁設計
tab_analyze, tab_iterate, tab_brief = st.tabs(["🧬 素材法醫 (Deconstruct)", "🧪 裂變工廠 (Iterate)", "📝 設計師工單 (Brief)"])

# === TAB 1: 素材法醫 (深度分析) ===
with tab_analyze:
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("### 📂 素材輸入")
        uploaded_file = st.file_uploader("上傳 MP4 (競品/自家素材)", type=["mp4"])
        game_type = st.selectbox("遊戲類型", ["MMORPG", "SLG (策略)", "卡牌 RPG", "超休閒 (Hyper-casual)", "博奕 (Casino)", "三消 (Match-3)"], index=1)
        kpi_focus = st.multiselect("關注指標", ["高消耗 (High Spend)", "高點擊 (High CTR)", "高轉化 (High CVR)", "低成本 (Low CPI)"], default=["高消耗 (High Spend)"])
        
        analyze_btn = st.button("🔥 開始逆向工程")

    with col2:
        if analyze_btn and uploaded_file and api_key:
            model = init_gemini(api_key)
            if model:
                # 存暫存檔
                temp_filename = "temp_ad.mp4"
                with open(temp_filename, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                # 上傳至 Gemini
                with st.spinner("正在將素材傳輸至雲端大腦..."):
                    video_file_gemini = upload_video_to_gemini(temp_filename)
                    st.session_state.video_file_ref = video_file_gemini
                
                if video_file_gemini:
                    # 2026 投手專用 Prompt
                    prompt = f"""
                    **角色設定**: 你是 2026 年最頂尖的手機遊戲廣告優化師 (UA Lead)，精通 AppGrowing、SensorTower 數據分析，並且深知人類多巴胺機制。
                    
                    **任務**: 分析這支「{game_type}」類型的遊戲廣告影片，告訴我它為什麼能獲得「{', '.join(kpi_focus)}」。
                    
                    請輸出以下結構的【深度診斷報告】(使用繁體中文 Markdown):

                    ### 1. 👁️ 黃金前 3 秒 (The Hook) - 決定生死的關鍵
                    *   **視覺衝擊**: 第一個畫面是什麼？(例如：巨物恐懼、大量金幣掉落、美女、甚至是故意失敗的操作)
                    *   **聽覺刺激**: 有無 ASMR？激昂 BGM？或是 AI 語音旁白？
                    *   **心理鉤子**: 利用了什麼人性弱點？(貪婪、色慾、強迫症、從眾心理、優越感)
                    
                    ### 2. 🧠 內容拆解 (The Body)
                    *   **素材類型**: 是 真人劇情(Live Action)、虛假玩法(Fake Gameplay)、真實錄屏(Real Gameplay) 還是 CG 動畫？
                    *   **節奏分析**: 剪輯節奏是快還是慢？有無反轉？
                    *   **核心痛點/爽點**: 影片展示了什麼解決方案或快感來源？
                    
                    ### 3. 🎯 轉化誘導 (The CTA)
                    *   **最終畫面**: 停留在什麼畫面？
                    *   **誘導話術**: 既然是「{game_type}」，它用了什麼誘因？(例如：送1000抽、戰力+999、限時領取)

                    ### 4. 💡 投手總結 (Media Buyer Verdict)
                    *   **爆量評分**: (1-10分，請嚴格評分)
                    *   **為什麼會跑量**: 請用一句話總結它的底層邏輯 (例如：用超休閒的玩法包裝重度 SLG，降低了用戶下載門檻)。
                    """
                    
                    with st.spinner("AI 正在逐幀解構爆量邏輯..."):
                        response = model.generate_content([video_file_gemini, prompt])
                        st.session_state.analysis_result = response.text
                        st.success("✅ 分析完成！")
                        
                        # 清理暫存
                        os.remove(temp_filename)

    # 顯示結果
    if st.session_state.analysis_result:
        st.markdown("---")
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.markdown(st.session_state.analysis_result)
        st.markdown('</div>', unsafe_allow_html=True)

# === TAB 2: 裂變工廠 (素材優化與翻拍) ===
with tab_iterate:
    st.markdown("### 🧪 A/B Test 素材裂變引擎")
    st.info("基於分析結果，生成 5 種不同的翻拍方向，延長素材壽命 (Life-cycle)。")
    
    if st.session_state.analysis_result and st.session_state.video_file_ref:
        direction = st.radio("優化方向", ["保留玩法，換開頭 (Remix Hook)", "保留開頭，換BGM/配音 (Remix Audio)", "完全翻拍 (Deep Fake/UGC)", "針對特定節日 (Seasonal)"])
        
        if st.button("⚡ 生成裂變方案"):
            model = init_gemini(api_key)
            iter_prompt = f"""
            **任務**: 基於上述的廣告分析報告，針對「{direction}」這個方向，提供 5 個具體的 A/B Test 變體 (Variants)。
            **目標**: 降低 CPI，提高 ROAS。
            
            請以表格呈現：
            | 變體編號 | 變更點 (What changed) | 預期效果/心理假設 (Hypothesis) | 製作難度 (低/中/高) |
            | :--- | :--- | :--- | :--- |
            | V1 | (例如：開頭改成真人美女驚訝表情) | (例如：利用性吸引力提升前3秒留存) | 低 |
            ...
            
            並在最後給出一個「大膽嘗試 (Wildcard)」的建議，完全跳脫現有框架。
            """
            
            with st.spinner("正在計算最佳 A/B Test 路徑..."):
                # 注意：這裡我們需要把之前的對話 context 帶入，或者直接把分析結果作為 prompt 的一部分
                full_prompt = f"分析報告:\n{st.session_state.analysis_result}\n\n指令:\n{iter_prompt}"
                # 這裡為了簡單，直接傳送 prompt 與 video (雖然 video 在這步其實非必要，但為了保持 context 也可以)
                # 為了省 token，我們直接用 text-to-text 即可，因為分析報告已有詳情
                response_iter = model.generate_content(full_prompt)
                st.markdown(response_iter.text)
    else:
        st.warning("請先在「素材法醫」分頁完成影片分析。")

# === TAB 3: 設計師工單 (Brief Generator) ===
with tab_brief:
    st.markdown("### 📝 Motion Designer 需求單自動生成")
    st.caption("將優化師的思維直接轉譯為設計師看得懂的分鏡腳本。")
    
    if st.session_state.analysis_result:
        brief_style = st.selectbox("需求單風格", ["詳細分鏡表 (Storyboard)", "快速修改單 (Quick Edit)", "UGC 網紅拍攝腳本"])
        
        if st.button("📄 產出需求單"):
            model = init_gemini(api_key)
            brief_prompt = f"""
            **任務**: 將分析報告轉化為一份專業的「{brief_style}」。
            **對象**: 公司的美術設計師或外包剪輯師。
            
            格式要求：
            1. **專案名稱**: [自動命名]
            2. **參考素材**: (描述原始影片特點)
            3. **核心修改需求**: 
            4. **詳細腳本 (時間軸 | 畫面 | 音效/口播 | 備註)**
            
            請確保語言精簡、指令明確，減少設計師的溝通成本。
            """
            
            full_prompt_brief = f"原始分析:\n{st.session_state.analysis_result}\n\n指令:\n{brief_prompt}"
            response_brief = model.generate_content(full_prompt_brief)
            
            st.text_area("複製以下內容給設計師", value=response_brief.text, height=400)
    else:
        st.warning("請先完成分析。")

# --- Footer ---
st.markdown("---")
st.markdown("© 2026 GameAd Intelligence Unit | Built for High Scalability")