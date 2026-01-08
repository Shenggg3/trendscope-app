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
    .report-card { background: #161b22; border: 1px solid #30363d; padding: 16px; border-radius: 10px; border-top: 3px solid #58a6ff; margin-bottom: 15px; }
    .shot-box { background: #161b22; border: 1px solid #30363d; border-radius: 12px; margin-bottom: 20px; overflow: hidden; }
    .ins-code { font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: #7ee787; background: #010409; padding: 12px; border-radius: 8px; border: 1px solid #30363d; line-height: 1.4; word-break: break-all; }
</style>
""", unsafe_allow_html=True)

# --- 2. 核心工具函數 ---

def call_gemini_with_retry(model_name, contents, api_key, max_retries=3):
    if not api_key:
        return "ERROR: Missing API Key"
    try:
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
    except Exception as e:
        return f"ERROR: Configuration failed {str(e)}"
    return "ERROR: Max retries exceeded"

def safe_json_parse(text):
    if not text or "ERROR:" in text: return {}
    clean_text = re.sub(r'```json\s*|\s*```', '', text).strip()
    try:
        return json.loads(clean_text)
    except:
        try:
            match = re.search(r'\{.*\}', clean_text, re.DOTALL)
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
        regex = r"(?:v=|\/|shorts\/|be\/)([0-9A-Za-z_-]{11})"
        match = re.search(regex, url)
        if not match: return f"無效網址: {url}"
        vid = match.group(1)
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', '未知標題')
            try:
                t = YouTubeTranscriptApi.get_transcript(vid, languages=['zh-TW', 'zh', 'en'])
                script = " ".join([x['text'] for x in t])
            except: script = "[無法獲取字幕]"
            return f"標題: {title}\n字幕: {script}"
    except Exception as e: return f"解析失敗: {str(e)}"

# --- 3. 初始化 Session ---
if 'step' not in st.session_state:
    st.session_state.update({
        'step': 1, 'api_connected': False, 'api_key': "", 'active_model': "gemini-1.5-flash",
        'psy_analysis': {}, 'game_dna': {}, 'final_script': {}, 
        'ref_data_text': "", 'target_game': "Last War", 
        'duration': 30, 'style_preset': "死侍式賤萌", 'custom_style': "", 
        'yt_urls_raw': "", 'gemini_video_refs': []
    })

# --- 4. 側邊欄 ---
with st.sidebar:
    st.markdown("### 🛡️ 指揮中心")
    # 將 API key 存入 session_state
    temp_key = st.text_input("輸入 Gemini API Key", value=st.session_state.api_key, type="password")
    if temp_key:
        st.session_state.api_key = temp_key

    if st.session_state.api_key:
        try:
            genai.configure(api_key=st.session_state.api_key)
            if not st.session_state.api_connected:
                models = [m.name.split('/')[-1] for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                st.session_state.active_model = st.selectbox("選擇 AI 模型", models, index=0)
                if st.button("🔗 測試連線"):
                    test_res = call_gemini_with_retry(st.session_state.active_model, "Ping", st.session_state.api_key)
                    if "ERROR" not in test_res:
                        st.session_state.api_connected = True
                        st.success("✅ 連線成功")
                        st.rerun()
                    else: st.error(test_res)
            else:
                st.success(f"● 已連線: {st.session_state.active_model}")
                if st.button("🔓 更換模型"):
                    st.session_state.api_connected = False
                    st.rerun()
        except Exception as e:
            st.error(f"連線錯誤: {e}")
    
    st.divider()
    if st.button("🔴 重置系統"):
        for k in list(st.session_state.keys()): del st.session_state[k]
        st.rerun()

# --- 5. 主視覺與導航 ---
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
    st.session_state.target_game = st.text_input("🎯 目標遊戲名稱", value=st.session_state.target_game)
    st.session_state.yt_urls_raw = st.text_area("🔗 YouTube 連結 (一行一個)", value=st.session_state.yt_urls_raw, height=120)
    uploaded_videos = st.file_uploader("📁 上傳參考影片", accept_multiple_files=True, type=['mp4', 'mov', 'avi'])

    if st.button("🚀 啟動並行分析", type="primary", use_container_width=True):
        if not st.session_state.api_connected:
            st.error("請先在側邊欄連線 API"); st.stop()
        
        with st.status("正在處理素材...", expanded=True) as status:
            # 修復點：確保使用 session_state 內的變數且避免區域變數衝突
            urls = [u.strip() for u in st.session_state.yt_urls_raw.split('\n') if u.strip()]
            ref_texts = []
            for u in urls:
                status.write(f"抓取中: {u}")
                ref_texts.append(fetch_yt_info(u))
            st.session_state.ref_data_text = "\n---\n".join(ref_texts)
            
            st.session_state.gemini_video_refs = []
            if uploaded_videos:
                for video in uploaded_videos:
                    status.write(f"上傳影片中: {video.name}")
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
                        tmp.write(video.read())
                        tmp_path = tmp.name
                    f_ref = genai.upload_file(tmp_path)
                    while f_ref.state.name == "PROCESSING":
                        time.sleep(2)
                        f_ref = genai.get_file(f_ref.name)
                    st.session_state.gemini_video_refs.append(f_ref)
                    os.remove(tmp_path)
            
            st.session_state.step = 2
            st.rerun()

# --- STEP 2: 心理調研 ---
elif st.session_state.step == 2:
    st.markdown("### 📊 素材心理基因報告")
    if not st.session_state.psy_analysis:
        with st.spinner("AI 正在分析戰略邏輯..."):
            contents = [f"{TC_ONLY}\n分析以下素材的心理戰術邏輯並以 JSON 格式輸出內容：hook_logic, conflict_pattern, pacing_rhythm, visual_saliency, reward_penalty, bartle_motivation, sound_logic, persuasion_arc, user_friction, emotional_hook。參考文本：{st.session_state.ref_data_text}"]
            contents.extend(st.session_state.gemini_video_refs)
            
            psy_raw = call_gemini_with_retry(st.session_state.active_model, contents, st.session_state.api_key)
            st.session_state.psy_analysis = safe_json_parse(psy_raw)

    psy = st.session_state.psy_analysis
    if not psy:
        st.warning("未能獲取分析數據，請點擊重試。")
        if st.button("重新分析"): st.session_state.psy_analysis = {}; st.rerun()
    else:
        labels = {"hook_logic":"🪝 Hook 邏輯", "conflict_pattern":"⚔️ 衝突模式", "pacing_rhythm":"⏱️ 節奏律動", "visual_saliency":"👁️ 視覺權重", "reward_penalty":"🏆 獎懲邏輯", "bartle_motivation":"🧠 玩家動機", "sound_logic":"🎵 聲音設計", "persuasion_arc":"🎢 說服弧線", "user_friction":"🚧 用戶阻力", "emotional_hook":"🎭 情緒留存"}
        cols = st.columns(2)
        for i, (k, label) in enumerate(labels.items()):
            with cols[i % 2]:
                st.markdown(f"<div class='report-card'><h4>{label}</h4><p>{psy.get(k, 'N/A')}</p></div>", unsafe_allow_html=True)
        
        if st.button("🚀 下一步：配置 DNA", type="primary", use_container_width=True):
            st.session_state.step = 3; st.rerun()

# --- STEP 3: DNA 與風格配置 ---
elif st.session_state.step == 3:
    st.markdown("### 🧬 戰術配置中心")
    if not st.session_state.game_dna:
        with st.spinner("獲取遊戲 DNA 中..."):
            dna_raw = call_gemini_with_retry(st.session_state.active_model, f"{TC_ONLY}\n分析《{st.session_state.target_game}》並輸出 JSON: genre, description, objects, visual_style", st.session_state.api_key)
            st.session_state.game_dna = safe_json_parse(dna_raw)

    with st.form("dna_form"):
        dna = st.session_state.game_dna
        dna['genre'] = st.text_input("📍 遊戲類型", value=dna.get('genre', ''))
        st.session_state.duration = st.slider("⏱️ 腳本秒數", 15, 60, st.session_state.duration)
        dna['objects'] = st.text_area("📦 核心物件 (影響畫面內容)", value=str(dna.get('objects', '')), height=100)
        st.session_state.style_preset = st.selectbox("🎭 語氣風格", ["死侍式賤萌", "諾蘭式史詩", "日系吐槽", "自定義"])
        
        if st.form_submit_button("💾 儲存並下一步"):
            st.session_state.game_dna = dna
            st.session_state.step = 4
            st.rerun()

# --- STEP 4: 腳本生成 ---
elif st.session_state.step == 4:
    st.markdown("### 🎬 生成結果")
    if not st.session_state.final_script:
        with st.spinner("正在執行創意生成..."):
            tone = st.session_state.style_preset
            prompt = f"""{TC_ONLY}
            時長: {st.session_state.duration}s | 風格: {tone}
            心理框架: {json.dumps(st.session_state.psy_analysis, ensure_ascii=False)}
            遊戲 DNA: {json.dumps(st.session_state.game_dna, ensure_ascii=False)}
            
            請輸出 JSON 格式：{{ "strategy_note": "...", "script_steps": [ {{ "time_range": "...", "action": "...", "dialogue": "...", "psychology_check": "...", "image_prompt": "...", "motion_prompt": "..." }} ] }}
            Image/Motion Prompts 務必使用英文並包含 '--ar 9:16'。
            """
            res = call_gemini_with_retry(st.session_state.active_model, prompt, st.session_state.api_key)
            st.session_state.final_script = safe_json_parse(res)

    fs = st.session_state.final_script
    if fs:
        st.info(f"💡 戰略核心：{fs.get('strategy_note')}")
        for i, s in enumerate(fs.get('script_steps', [])):
            st.markdown(f"""
            <div class='shot-box'>
                <div style='background:#21262d; padding:10px 20px; color:#58a6ff; font-weight:bold;'>分鏡 {i+1} ({s.get('time_range')}s)</div>
                <div style='padding:20px;'>
                    <div style='color:#ffa657; font-size:1.2rem; font-weight:bold;'>{s.get('action')}</div>
                    <div style='background:#0d1117; padding:15px; margin:10px 0; border-left:4px solid #bc8cff;'>{s.get('dialogue')}</div>
                    <div class='ins-code'>{s.get('image_prompt')}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        if st.button("🔄 重新生成腳本"):
            st.session_state.final_script = {}
            st.rerun()