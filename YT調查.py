import streamlit as st
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp
import os
import time
import re
import json
import tempfile
from docx import Document
from io import BytesIO
from google.api_core import exceptions

# --- 1. UIUX 專業樣式定義 ---
st.set_page_config(page_title="UA Sovereign Pro", page_icon="👑", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=JetBrains+Mono&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; background-color: #0D1117; color: #C9D1D9; }
    .main-title { font-size: 2.8rem; font-weight: 900; background: linear-gradient(90deg, #58a6ff, #bc8cff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .report-card { background: #161b22; border: 1px solid #30363d; padding: 16px; border-radius: 10px; border-top: 3px solid #58a6ff; }
    .dna-panel { background: #161b22; border: 1px solid #30363d; padding: 25px; border-radius: 15px; }
    .shot-box { background: #161b22; border: 1px solid #30363d; border-radius: 12px; margin-bottom: 20px; overflow: hidden; }
    .ins-code { font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: #7ee787; background: #010409; padding: 12px; border-radius: 8px; border: 1px solid #30363d; line-height: 1.4; }
    .stTextArea textarea { background-color: #010409 !important; border: 1px solid #30363d !important; color: #7ee787 !important; font-family: 'JetBrains Mono' !important; }
</style>
""", unsafe_allow_html=True)

# --- 2. 核心核心工具函數 ---

def call_gemini_with_retry(model_name, contents, api_key, max_retries=3):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    for i in range(max_retries):
        try:
            res = model.generate_content(contents)
            return res.text
        except exceptions.ResourceExhausted:
            time.sleep((i + 1) * 10)
        except Exception as e:
            st.error(f"❌ API 執行錯誤: {str(e)}")
            return None
    return None

def safe_json_parse(text):
    if not text: return {}
    text = re.sub(r'```json\s*|\s*```', '', text).strip()
    try:
        return json.loads(text)
    except:
        try:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match: return json.loads(match.group())
        except: pass
    return {}

def create_docx_report(data, title="Report"):
    doc = Document()
    doc.add_heading(title, 0)
    if isinstance(data, dict):
        for k, v in data.items():
            doc.add_heading(str(k), level=1)
            doc.add_paragraph(str(v))
    else:
        doc.add_paragraph(str(data))
    bio = BytesIO()
    doc.save(bio)
    return bio.getvalue()

def fetch_yt_info(url):
    try:
        vid = re.search(r"(?:v=|\/|shorts\/)([0-9A-Za-z_-]{11})", url).group(1)
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            try:
                t = YouTubeTranscriptApi.get_transcript(vid, languages=['zh-TW', 'zh', 'en'])
                script = " ".join([x['text'] for x in t])
            except: script = "[無法獲取字幕]"
            return f"標題: {info.get('title')}\n內容: {script}"
    except: return ""

# --- 3. 初始化 Session ---
init_keys = {
    'step': 1, 'api_connected': False, 'psy_analysis': {}, 'game_dna': {}, 
    'final_script': {}, 'ref_data_text': "", 'target_game': "Last War", 
    'duration': 30, 'style_preset': "死侍式賤萌", 'custom_style': "", 'yt_urls_raw': "", 'gemini_video_refs': []
}
for k, v in init_keys.items():
    if k not in st.session_state: st.session_state[k] = v

# --- 4. 側邊欄與 API 狀態 ---
with st.sidebar:
    st.markdown("### 🛡️ 指揮中心")
    user_key = st.text_input("輸入 API Key", type="password")
    if user_key:
        try:
            genai.configure(api_key=user_key)
            models = [m.name.split('/')[-1] for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            sel_model = st.selectbox("選擇 AI 模型", models, index=models.index("gemini-1.5-flash") if "gemini-1.5-flash" in models else 0)
            if st.button("🔗 測試並鎖定連線"):
                if call_gemini_with_retry(sel_model, "Ping", user_key):
                    st.session_state.api_connected = True
                    st.session_state.active_model = sel_model
                    st.success("✅ 模型已連線")
        except: st.error("❌ Key 無效")
    
    if st.session_state.api_connected:
        st.markdown(f'<div style="color:#3fb950;padding:10px;font-weight:bold;text-align:center;">● 在線: {st.session_state.active_model}</div>', unsafe_allow_html=True)
    
    st.divider()
    if st.button("🔴 重置系統與清理雲端"):
        if st.session_state.api_connected:
            try:
                for f in genai.list_files(): genai.delete_file(f.name)
            except: pass
        for k in list(st.session_state.keys()): del st.session_state[k]
        st.rerun()

# --- 5. 主視覺導航 ---
st.markdown("<h1 class='main-title'>UA Sovereign Pro 👑</h1>", unsafe_allow_html=True)

nav_col = st.columns(4)
nav_labels = ["1. 素材注入", "2. 心理調研", "3. 戰術與 DNA", "4. 腳本生成"]
for i, label in enumerate(nav_labels):
    if nav_col[i].button(label, use_container_width=True, type="primary" if st.session_state.step == i+1 else "secondary"):
        st.session_state.step = i+1
        st.rerun()

TC_ONLY = "注意：除了生成的 Image/Motion Prompt 必須使用英文，其餘輸出務必使用『繁體中文 (zh-TW)』。嚴禁簡體。"

# --- STEP 1: 素材注入 ---
if st.session_state.step == 1:
    c1, c2 = st.columns(2)
    with c1:
        st.session_state.target_game = st.text_input("🎯 目標遊戲名稱", value=st.session_state.target_game)
    with c2:
        st.info("💡 提醒：分析參考片後，您將在步驟 3 配置物件庫與時長。")

    st.session_state.yt_urls_raw = st.text_area("🔗 YouTube 連結 (一行一個)", value=st.session_state.yt_urls_raw, height=120)
    uploaded_videos = st.file_uploader("📁 上傳參考影片 (可多選)", accept_multiple_files=True, type=['mp4', 'mov', 'avi'])

    if st.button("🚀 第一步：啟動並行分析", type="primary", use_container_width=True):
        if not st.session_state.api_connected: st.error("請先在側邊欄連線"); st.stop()
        with st.status("正在注入多模態素材...", expanded=True) as status:
            st.session_state.ref_data_text = "\n---\n".join([fetch_yt_info(u) for u in yt_urls.split('\n') if u.strip()])
            st.session_state.gemini_video_refs = []
            if uploaded_videos:
                for video in uploaded_videos:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
                        tmp.write(video.read()); tmp_path = tmp.name
                    f_ref = genai.upload_file(tmp_path)
                    while f_ref.state.name == "PROCESSING": time.sleep(2); f_ref = genai.get_file(f_ref.name)
                    st.session_state.gemini_video_refs.append(f_ref)
                    os.remove(tmp_path)
            st.session_state.step = 2; st.rerun()

# --- STEP 2: 心理調研 ---
elif st.session_state.step == 2:
    st.markdown("### 📊 素材心理基因報告")
    if not st.session_state.psy_analysis:
        with st.spinner("AI 正在觀看影片並解構戰略邏輯..."):
            contents = list(st.session_state.gemini_video_refs)
            contents.append(f"{TC_ONLY}\n請分析參考素材的『心理戰術框架』(禁止提到原片物件)。參考文字：{st.session_state.ref_data_text}\nJSON 輸出: hook_logic, conflict_pattern, pacing_rhythm, visual_saliency, reward_penalty, bartle_motivation, sound_logic, persuasion_arc, user_friction, emotional_hook.")
            psy_raw = call_gemini_with_retry(st.session_state.active_model, contents, user_key)
            st.session_state.psy_analysis = safe_json_parse(psy_raw)

    psy = st.session_state.psy_analysis
    labels = {"hook_logic":"🪝 Hook 邏輯", "conflict_pattern":"⚔️ 衝突模式", "pacing_rhythm":"⏱️ 節奏律動", "visual_saliency":"👁️ 視覺權重", "reward_penalty":"🏆 獎懲邏輯", "bartle_motivation":"🧠 玩家動機", "sound_logic":"🎵 聲音設計", "persuasion_arc":"🎢 說服弧線", "user_friction":"🚧 用戶阻力", "emotional_hook":"🎭 情緒留存"}
    
    st.markdown("<div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px;'>", unsafe_allow_html=True)
    for k, label in labels.items():
        st.markdown(f"<div class='report-card'><h4>{label}</h4><p>{psy.get(k, 'N/A')}</p></div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.divider()
    docx_psy = create_docx_report({labels[k]: psy.get(k) for k in labels}, title=f"{st.session_state.target_game} 心理戰研報告")
    st.download_button("📥 下載心理調研報告 (Word)", docx_psy, "Psy_Analysis.docx", use_container_width=True)
    
    if st.button("🚀 第二步：配置 DNA 與戰術", type="primary", use_container_width=True):
        st.session_state.step = 3; st.rerun()

# --- STEP 3: DNA 與風格校對 (UI 優化) ---
elif st.session_state.step == 3:
    st.markdown("### 🧬 戰術配置中心：DNA、時長與風格")
    if not st.session_state.game_dna:
        with st.spinner("調研自家遊戲中..."):
            dna_raw = call_gemini_with_retry(st.session_state.active_model, f"{TC_ONLY}\n分析《{st.session_state.target_game}》輸出 JSON: genre(類型), description(介紹), objects(物件), visual_style(風格描述)", user_key)
            st.session_state.game_dna = safe_json_parse(dna_raw)

    dna = st.session_state.game_dna
    with st.form("dna_form_final"):
        c1, c2 = st.columns(2)
        dna['genre'] = c1.text_input("📍 遊戲類型", value=dna.get('genre', ''))
        st.session_state.duration = c2.slider("⏱️ 最終腳本秒數時長", 15, 60, st.session_state.duration, step=5)
        
        dna['description'] = st.text_area("📝 遊戲介紹與背景", value=dna.get('description', ''), height=100)
        dna['objects'] = st.text_area("📦 核心物件清單 (影響腳本內容)", value=str(dna.get('objects', '')), height=150)
        dna['visual_style'] = st.text_area("🎨 視覺風格調性 (畫質、材質描述)", value=dna.get('visual_style', ''), height=100)
        
        st.session_state.style_preset = st.selectbox("🎭 創意風格語氣", ["死侍式賤萌", "諾蘭式史詩", "極速流反轉", "日系吐槽", "自定義"], index=["死侍式賤萌", "諾蘭式史詩", "極速流反轉", "日系吐槽", "自定義"].index(st.session_state.style_preset))
        if st.session_state.style_preset == "自定義":
            st.session_state.custom_style = st.text_area("自定義風格詳細描述", value=st.session_state.custom_style, height=80)
            
        if st.form_submit_button("💾 儲存戰略配置", use_container_width=True):
            st.session_state.game_dna = dna; st.toast("戰略 DNA 已同步！")
    
    if st.button("🚀 生成最終原創腳本", type="primary", use_container_width=True):
        st.session_state.step = 4; st.rerun()

# --- STEP 4: 腳本生成 (格式修復與導出) ---
elif st.session_state.step == 4:
    st.markdown("### 🎬 生成結果：跨維度原創腳本")
    final_tone = st.session_state.custom_style if st.session_state.style_preset == "自定義" else st.session_state.style_preset
    
    if st.button("🔄 重新杂交生成腳本"): st.session_state.final_script = {}; st.rerun()

    if not st.session_state.final_script:
        with st.spinner(f"正在以『{final_tone}』語氣執行創意合成..."):
            visual_enhancer = f"畫風: {st.session_state.game_dna.get('visual_style')}. 必須包含 '--ar 9:16', 'high fidelity'。"
            final_raw = call_gemini_with_retry(st.session_state.active_model, f"""{TC_ONLY}
            {visual_enhancer} | 時長: {st.session_state.duration} 秒 | 風格: {final_tone}
            心理框架: {json.dumps(st.session_state.psy_analysis, ensure_ascii=False)}
            可用物件: {json.dumps(st.session_state.game_dna, ensure_ascii=False)}
            
            輸出格式請務必為 JSON，結構如下:
            {{ "strategy_note": "...", "script_steps": [ {{ "time_range": "...", "action": "...", "dialogue": "...", "psychology_check": "...", "image_prompt": "...", "motion_prompt": "..." }} ] }}
            """, user_key)
            st.session_state.final_script = safe_json_parse(final_raw)

    fs = st.session_state.final_script
    if fs:
        st.success(f"💡 **戰略摘要**: {fs.get('strategy_note')}")
        script_text_for_word = f"創意戰略：{fs.get('strategy_note')}\n\n"
        
        for i, s in enumerate(fs.get('script_steps', [])):
            st.markdown(f"""
            <div class='shot-box'>
                <div style='background:#21262d; padding:12px 25px; display:flex; justify-content:space-between; align-items:center;'>
                    <b style="color: #58a6ff;">SHOT {i+1}</b> <span style='font-size:0.9rem; color:#8b949e;'>⏳ {s.get('time_range')}</span>
                </div>
                <div style='padding:25px; display:grid; grid-template-columns: 1.2fr 1fr; gap:30px;'>
                    <div>
                        <div style='color:#ffa657; font-size:1.3rem; font-weight:bold; margin-bottom:12px;'>{s.get('action')}</div>
                        <div style='background:#0d1117; padding:18px; border-radius:10px; border-left:4px solid #bc8cff;'>{s.get('dialogue')}</div>
                        <p style='font-size:0.85rem; color:#8b949e; margin-top:15px;'>🎯 心理: {s.get('psychology_check')}</p>
                    </div>
                    <div>
                        <span style='font-size:0.75rem; font-weight:bold; color:#8b949e;'>🖼️ IMAGE PROMPT</span>
                        <div class='ins-code'>{s.get('image_prompt')}</div>
                        <span style='font-size:0.75rem; font-weight:bold; color:#8b949e; margin-top:10px; display:block;'>🎥 MOTION PROMPT</span>
                        <div class='ins-code' style='color:#79c0ff;'>{s.get('motion_prompt')}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            script_text_for_word += f"分鏡 {i+1} [{s.get('time_range')}]: {s.get('action')}\n台詞：{s.get('dialogue')}\nImage Prompt: {s.get('image_prompt')}\nMotion Prompt: {s.get('motion_prompt')}\n\n"

        st.divider()
        docx_script = create_docx_report(script_text_for_word, title=f"{st.session_state.target_game} 原創 UA 分鏡腳本")
        st.download_button("📥 下載最終腳本分鏡表 (Word)", docx_script, "Final_Storyboard.docx", use_container_width=True)