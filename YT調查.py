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
st.set_page_config(page_title="影片UA影片生成 👑", page_icon="👑", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=JetBrains+Mono&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; background-color: #0D1117; color: #C9D1D9; }
    .main-title { font-size: 2.8rem; font-weight: 900; background: linear-gradient(90deg, #58a6ff, #bc8cff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .report-card { background: #161b22; border: 1px solid #30363d; padding: 16px; border-radius: 10px; border-top: 3px solid #58a6ff; margin-bottom: 12px; height: 100%; }
    .shot-box { background: #161b22; border: 1px solid #30363d; border-radius: 12px; margin-bottom: 20px; overflow: hidden; }
    .ins-code { font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: #7ee787; background: #010409; padding: 12px; border-radius: 8px; border: 1px solid #30363d; line-height: 1.4; word-break: break-all; }
    .stTextArea textarea { background-color: #010409 !important; border: 1px solid #30363d !important; color: #7ee787 !important; font-family: 'JetBrains Mono' !important; }
</style>
""", unsafe_allow_html=True)

# --- 2. 核心工具函數 ---

def call_gemini_with_retry(model_name, contents, api_key, max_retries=3):
    if not api_key: return "ERROR: No API Key"
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    for i in range(max_retries):
        try:
            res = model.generate_content(contents)
            return res.text
        except exceptions.ResourceExhausted:
            time.sleep((i + 1) * 5)
        except Exception as e:
            return f"ERROR: {str(e)}"
    return "ERROR: Max retries"

def safe_json_parse(text):
    if not text or "ERROR" in text: return {}
    clean_text = re.sub(r'```json\s*|\s*```', '', text).strip()
    try:
        return json.loads(clean_text)
    except:
        try:
            match = re.search(r'\{.*\}', clean_text, re.DOTALL)
            if match: return json.loads(match.group())
        except: pass
    return {}

def fetch_yt_info(url):
    try:
        vid_match = re.search(r"(?:v=|\/|shorts\/|be\/)([0-9A-Za-z_-]{11})", url)
        if not vid_match: return ""
        vid = vid_match.group(1)
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            try:
                t = YouTubeTranscriptApi.get_transcript(vid, languages=['zh-TW', 'zh', 'en'])
                script = " ".join([x['text'] for x in t])
            except: script = "[無法獲取字幕]"
            return f"標題: {info.get('title')}\n內容: {script}"
    except: return ""

def create_docx_report(text, title):
    doc = Document()
    doc.add_heading(title, 0)
    doc.add_paragraph(text)
    bio = BytesIO()
    doc.save(bio)
    return bio.getvalue()

# --- 3. 初始化 Session ---
init_keys = {
    'step': 1, 'api_connected': False, 'api_key': "", 'active_model': "gemini-2.5-flash",
    'psy_analysis': {}, 'game_dna': {}, 'final_script': {}, 
    'ref_data_text': "", 'target_game': " 寒霜啟示錄 ", 
    'duration': 30, 'style_preset': "死侍式賤萌", 'custom_style': "", 
    'yt_urls_raw': "", 'gemini_video_refs': []
}
for k, v in init_keys.items():
    if k not in st.session_state: st.session_state[k] = v

# --- 4. 側邊欄 ---
with st.sidebar:
    st.markdown("### 🛡️ 指揮中心")
    st.session_state.api_key = st.text_input("輸入 API Key", value=st.session_state.api_key, type="password")
    
    if st.session_state.api_key:
        try:
            genai.configure(api_key=st.session_state.api_key)
            if not st.session_state.api_connected:
                models = [m.name.split('/')[-1] for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                st.session_state.active_model = st.selectbox("選擇模型", models, index=0)
                if st.button("🔗 測試連線"):
                    if "ERROR" not in call_gemini_with_retry(st.session_state.active_model, "Ping", st.session_state.api_key):
                        st.session_state.api_connected = True
                        st.rerun()
            else:
                st.success(f"● 已連線: {st.session_state.active_model}")
                if st.button("🔓 更換模型"):
                    st.session_state.api_connected = False
                    st.rerun()
        except: st.error("Key 有誤")

    st.divider()
    if st.button("🔴 重置系統"):
        for k in list(st.session_state.keys()): del st.session_state[k]
        st.rerun()

# --- 5. 主導航 ---
st.markdown("<h1 class='main-title'>UA Sovereign Pro 👑</h1>", unsafe_allow_html=True)
nav_col = st.columns(4)
for i, label in enumerate(["1. 素材注入", "2. 心理調研", "3. 戰術與 DNA", "4. 腳本生成"]):
    if nav_col[i].button(label, use_container_width=True, type="primary" if st.session_state.step == i+1 else "secondary"):
        st.session_state.step = i+1
        st.rerun()

TC_ONLY = "注意：除了生成的 Image/Motion Prompt 必須使用英文，其餘輸出務必使用『繁體中文 (zh-TW)』。嚴禁簡體。"

# --- STEP 1: 素材注入 ---
if st.session_state.step == 1:
    st.session_state.target_game = st.text_input("🎯 目標遊戲名稱", value=st.session_state.target_game)
    st.session_state.yt_urls_raw = st.text_area("🔗 YouTube 連結 (一行一個)", value=st.session_state.yt_urls_raw, height=120)
    uploaded_files = st.file_uploader("📁 上傳參考影片", accept_multiple_files=True, type=['mp4','mov','avi'])

    if st.button("🚀 啟動並行分析", type="primary", use_container_width=True):
        if not st.session_state.api_connected: st.error("請先連線 API"); st.stop()
        with st.status("正在注入素材...") as status:
            urls = [u.strip() for u in st.session_state.yt_urls_raw.split('\n') if u.strip()]
            st.session_state.ref_data_text = "\n---\n".join([fetch_yt_info(u) for u in urls])
            st.session_state.gemini_video_refs = []
            for f in uploaded_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
                    tmp.write(f.read()); tmp_path = tmp.name
                g_file = genai.upload_file(tmp_path)
                while g_file.state.name == "PROCESSING": time.sleep(2); g_file = genai.get_file(g_file.name)
                st.session_state.gemini_video_refs.append(g_file)
                os.remove(tmp_path)
            st.session_state.step = 2; st.rerun()

# --- STEP 2: 心理調研 ---
elif st.session_state.step == 2:
    st.markdown("### 📊 素材心理基因報告")
    if not st.session_state.psy_analysis:
        with st.spinner("AI 正在解析心理戰術..."):
            prompt = f"{TC_ONLY}\n請分析參考素材的『心理戰術框架』(禁止提到原片物件)。參考文字：{st.session_state.ref_data_text}\nJSON 輸出: hook_logic, conflict_pattern, pacing_rhythm, visual_saliency, reward_penalty, bartle_motivation, sound_logic, persuasion_arc, user_friction, emotional_hook."
            res = call_gemini_with_retry(st.session_state.active_model, [prompt] + st.session_state.gemini_video_refs, st.session_state.api_key)
            st.session_state.psy_analysis = safe_json_parse(res)
    
    psy = st.session_state.psy_analysis
    labels = {"hook_logic":"🪝 Hook 邏輯", "conflict_pattern":"⚔️ 衝突模式", "pacing_rhythm":"⏱️ 節奏律動", "visual_saliency":"👁️ 視覺權重", "reward_penalty":"🏆 獎懲邏輯", "bartle_motivation":"🧠 玩家動機", "sound_logic":"🎵 聲音設計", "persuasion_arc":"🎢 說服弧線", "user_friction":"🚧 用戶阻力", "emotional_hook":"🎭 情緒留存"}
    cols = st.columns(2)
    for i, (k, v) in enumerate(labels.items()):
        with cols[i%2]: st.markdown(f"<div class='report-card'><h4>{v}</h4><p>{psy.get(k, 'N/A')}</p></div>", unsafe_allow_html=True)
    
    if st.button("🚀 下一步：配置 DNA", type="primary", use_container_width=True):
        st.session_state.step = 3; st.rerun()

# --- STEP 3: DNA 與戰術配置 (修正自動調查與自定義功能) ---
elif st.session_state.step == 3:
    st.markdown("### 🧬 戰術配置中心：DNA 與風格")
    
    # 修正點：自動調查遊戲 DNA
    if not st.session_state.game_dna:
        with st.spinner(f"正在深度分析《{st.session_state.target_game}》的遊戲 DNA..."):
            dna_prompt = f"{TC_ONLY}\n請深入調查並分析遊戲《{st.session_state.target_game}》，輸出 JSON: genre(遊戲類型), description(遊戲介紹), objects(核心視覺物件與角色清單), visual_style(美術風格與畫質描述)。"
            dna_res = call_gemini_with_retry(st.session_state.active_model, dna_prompt, st.session_state.api_key)
            st.session_state.game_dna = safe_json_parse(dna_res)

    dna = st.session_state.game_dna
    with st.form("dna_form"):
        c1, c2 = st.columns(2)
        dna['genre'] = c1.text_input("📍 遊戲類型", value=dna.get('genre', ''))
        st.session_state.duration = c2.slider("⏱️ 最終腳本秒數", 15, 60, st.session_state.duration, step=5)
        
        dna['description'] = st.text_area("📝 遊戲介紹", value=dna.get('description', ''), height=100)
        dna['objects'] = st.text_area("📦 核心物件清單", value=str(dna.get('objects', '')), height=100)
        dna['visual_style'] = st.text_area("🎨 視覺風格描述", value=dna.get('visual_style', ''), height=80)
        
        # 修正點：自定義風格邏輯
        st.session_state.style_preset = st.selectbox("🎭 創意語氣風格", ["死侍式賤萌", "諾蘭式史詩", "極速流反轉", "日系吐槽", "自定義"], index=["死侍式賤萌", "諾蘭式史詩", "極速流反轉", "日系吐槽", "自定義"].index(st.session_state.style_preset))
        
        if st.session_state.style_preset == "自定義":
            st.session_state.custom_style = st.text_area("✍️ 請輸入自定義風格描述", value=st.session_state.custom_style, placeholder="例如：類似於魏斯·安德森的對稱美學與冷幽默，節奏明快...")
            
        if st.form_submit_button("💾 儲存並同步戰略配置", use_container_width=True):
            st.session_state.game_dna = dna
            st.toast("戰略 DNA 已更新！")

    if st.button("🚀 生成最終原創腳本", type="primary", use_container_width=True):
        st.session_state.step = 4; st.rerun()

# --- STEP 4: 腳本生成 (恢復卡片佈局與高質量輸出) ---
elif st.session_state.step == 4:
    st.markdown("### 🎬 生成結果：跨維度原創腳本")
    final_tone = st.session_state.custom_style if st.session_state.style_preset == "自定義" else st.session_state.style_preset

    if not st.session_state.final_script:
        with st.spinner(f"正在以「{final_tone}」風格合成腳本..."):
            prompt = f"""{TC_ONLY}
            請為《{st.session_state.target_game}》創作一則原創 UA 廣告腳本。
            畫風需求: {st.session_state.game_dna.get('visual_style')}。
            時長: {st.session_state.duration} 秒 | 語氣風格: {final_tone}
            心理框架參考: {json.dumps(st.session_state.psy_analysis, ensure_ascii=False)}
            可用物件: {st.session_state.game_dna.get('objects')}
            
            輸出格式務必為 JSON:
            {{ "strategy_note": "戰略摘要", "script_steps": [ {{ "time_range": "00-03", "action": "畫面描述", "dialogue": "台詞", "psychology_check": "心理邏輯", "image_prompt": "英文提示詞", "motion_prompt": "英文動態提示詞" }} ] }}
            Prompt 須包含 '--ar 9:16', 'high fidelity'。
            """
            res = call_gemini_with_retry(st.session_state.active_model, prompt, st.session_state.api_key)
            st.session_state.final_script = safe_json_parse(res)

    fs = st.session_state.final_script
    if fs:
        st.success(f"💡 **創意戰略**: {fs.get('strategy_note')}")
        for i, s in enumerate(fs.get('script_steps', [])):
            st.markdown(f"""
            <div class='shot-box'>
                <div style='background:#21262d; padding:12px 25px; display:flex; justify-content:space-between;'>
                    <b style="color:#58a6ff;">SHOT {i+1}</b> <span style='color:#8b949e;'>⏳ {s.get('time_range')}s</span>
                </div>
                <div style='padding:25px; display:grid; grid-template-columns: 1.2fr 1fr; gap:25px;'>
                    <div>
                        <div style='color:#ffa657; font-size:1.2rem; font-weight:bold; margin-bottom:10px;'>{s.get('action')}</div>
                        <div style='background:#0d1117; padding:15px; border-radius:10px; border-left:4px solid #bc8cff;'>{s.get('dialogue')}</div>
                        <p style='font-size:0.85rem; color:#8b949e; margin-top:12px;'>🎯 心理戰術: {s.get('psychology_check')}</p>
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
        
        docx_data = create_docx_report(str(fs), f"{st.session_state.target_game} 腳本")
        st.download_button("📥 下載完整分鏡表 (Word)", docx_data, "Script.docx", use_container_width=True)
        if st.button("🔄 重新生成"): st.session_state.final_script = {}; st.rerun()