import streamlit as st
import openai
import os
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import config

st.set_page_config(
    page_title="Stelic Copilot",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- Power BI matched styling ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif !important;
        background-color: #ffffff !important;
    }

    #MainMenu, header, footer, .stDeployButton { display: none !important; }

    .block-container {
        padding: 0rem 0.75rem 0.5rem 0.75rem !important;
        max-width: 100% !important;
    }

    /* Header bar matching Power BI navy */
    .copilot-header {
        background: linear-gradient(90deg, #1a3a5c 0%, #0078D4 100%);
        color: white;
        padding: 10px 14px;
        border-radius: 4px 4px 0 0;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 0;
    }
    .copilot-header span {
        font-size: 14px;
        font-weight: 600;
        letter-spacing: 0.3px;
    }
    .copilot-subheader {
        background: #f0f6ff;
        border: 1px solid #cce0f5;
        border-top: none;
        padding: 5px 14px;
        font-size: 11px;
        color: #0078D4;
        margin-bottom: 8px;
        border-radius: 0 0 4px 4px;
    }

    /* Chat messages */
    [data-testid="stChatMessage"] {
        font-size: 13px !important;
        font-family: 'Segoe UI', sans-serif !important;
        padding: 6px 10px !important;
        border-radius: 4px !important;
    }

    [data-testid="stChatMessage"][data-testid*="user"] {
        background-color: #e8f2fc !important;
    }

    /* Input box */
    [data-testid="stChatInputContainer"] {
        border: 1.5px solid #0078D4 !important;
        border-radius: 4px !important;
        background: #f9fbfe !important;
    }

    textarea[data-testid="stChatInputTextArea"] {
        font-size: 13px !important;
        font-family: 'Segoe UI', sans-serif !important;
    }

    /* Upload expander */
    .streamlit-expanderHeader {
        font-size: 12px !important;
        color: #0078D4 !important;
        font-family: 'Segoe UI', sans-serif !important;
    }

    /* Divider */
    hr { border-color: #e0eaf4 !important; margin: 6px 0 !important; }

    /* Quick buttons */
    .stButton > button {
        background-color: #f0f6ff !important;
        color: #0078D4 !important;
        border: 1px solid #cce0f5 !important;
        border-radius: 3px !important;
        font-size: 11px !important;
        padding: 3px 8px !important;
        font-family: 'Segoe UI', sans-serif !important;
        width: 100% !important;
    }
    .stButton > button:hover {
        background-color: #0078D4 !important;
        color: white !important;
    }

    /* File uploader */
    [data-testid="stFileUploader"] {
        border: 1px dashed #0078D4 !important;
        border-radius: 4px !important;
        padding: 6px !important;
        background: #f9fbfe !important;
    }
    [data-testid="stFileUploader"] label { font-size: 11px !important; color: #555 !important; }
</style>
""", unsafe_allow_html=True)

# --- Header ---
st.markdown("""
<div class="copilot-header">
    <span>🤖 Stelic Copilot</span>
</div>
<div class="copilot-subheader">
    AI assistant · Project schedules, documents & data
</div>
""", unsafe_allow_html=True)

# --- Session state ---
if "panel_messages" not in st.session_state:
    st.session_state.panel_messages = []
if "panel_context" not in st.session_state:
    st.session_state.panel_context = ""
if "panel_image_payload" not in st.session_state:
    st.session_state.panel_image_payload = None

# --- API client ---
def get_client():
    api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
    base_url = config.get("api_base_url")
    if not api_key:
        return None
    return openai.OpenAI(api_key=api_key, base_url=base_url)

# --- File upload ---
with st.expander("📎 Attach file or screenshot", expanded=False):
    uploaded = st.file_uploader(
        "XER, XML, PDF, image, CSV, or text",
        type=["xer", "xml", "pdf", "txt", "md", "png", "jpg", "jpeg", "csv"],
        key="panel_upload",
        label_visibility="collapsed"
    )

    if uploaded:
        file_type = uploaded.name.split(".")[-1].lower()

        if file_type in ["png", "jpg", "jpeg"]:
            st.image(uploaded, caption=uploaded.name, use_container_width=True)
            img_bytes = uploaded.read()
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            mime = "image/jpeg" if file_type in ["jpg", "jpeg"] else "image/png"
            st.session_state.panel_image_payload = {"mime": mime, "b64": b64, "name": uploaded.name}
            st.session_state.panel_context = f"[Image attached: {uploaded.name}]"
            st.success(f"✅ Image ready — will be included in next message")

        elif file_type == "xer":
            try:
                from parser import XERParser
                from analyzer import ScheduleAnalyzer
                import io
                raw = uploaded.read()
                parser = XERParser(io.BytesIO(raw), uploaded.name)
                analyzer = ScheduleAnalyzer(parser)
                ctx = parser.get_llm_context()
                metrics = ctx.get("project_metrics", {})
                project = ctx.get("project_info", {})
                st.session_state.panel_context = (
                    f"SCHEDULE CONTEXT — Project: {project.get('name','Unknown')} | "
                    f"Data Date: {project.get('data_date','N/A')} | "
                    f"Total Activities: {metrics.get('total_activities',0)} | "
                    f"Complete: {metrics.get('completed',0)} | "
                    f"Active: {metrics.get('in_progress',0)} | "
                    f"Not Started: {metrics.get('not_started',0)} | "
                    f"Progress: {metrics.get('percent_complete','0%')}"
                )
                st.session_state.panel_image_payload = None
                st.success(f"✅ Schedule loaded: {project.get('name','XER file')}")
            except Exception as e:
                st.error(f"❌ Could not parse XER: {str(e)[:80]}")

        elif file_type in ["txt", "md", "csv"]:
            try:
                text = uploaded.read().decode("utf-8", errors="ignore")
                st.session_state.panel_context = f"[File: {uploaded.name}]\n{text[:3000]}"
                st.session_state.panel_image_payload = None
                st.success(f"✅ {uploaded.name} loaded as context")
            except Exception as e:
                st.error(f"❌ Could not read file: {str(e)[:80]}")

        elif file_type == "pdf":
            try:
                import io
                raw = uploaded.read()
                try:
                    import pypdf
                    reader = pypdf.PdfReader(io.BytesIO(raw))
                    text = "\n".join(page.extract_text() or "" for page in reader.pages[:10])
                except ImportError:
                    text = "[PDF uploaded — install pypdf for text extraction]"
                st.session_state.panel_context = f"[PDF: {uploaded.name}]\n{text[:3000]}"
                st.session_state.panel_image_payload = None
                st.success(f"✅ PDF loaded: {uploaded.name}")
            except Exception as e:
                st.error(f"❌ Could not read PDF: {str(e)[:80]}")

        elif file_type == "xml":
            try:
                text = uploaded.read().decode("utf-8", errors="ignore")
                st.session_state.panel_context = f"[XML Schedule: {uploaded.name}]\n{text[:3000]}"
                st.session_state.panel_image_payload = None
                st.success(f"✅ XML loaded: {uploaded.name}")
            except Exception as e:
                st.error(f"❌ Could not read XML: {str(e)[:80]}")

    if st.session_state.panel_context:
        st.caption(f"📌 Context active: {st.session_state.panel_context[:80]}...")
        if st.button("✕ Clear context", key="clear_ctx"):
            st.session_state.panel_context = ""
            st.session_state.panel_image_payload = None
            st.rerun()

st.divider()

# --- Quick questions ---
st.markdown('<p style="font-size:11px;color:#6c757d;margin-bottom:4px">Quick questions:</p>', unsafe_allow_html=True)
col1, col2, col3 = st.columns(3)
quick_questions = {
    "col1": "Project status?",
    "col2": "Top risks?",
    "col3": "Critical path?"
}
for col, q in zip([col1, col2, col3], quick_questions.values()):
    with col:
        if st.button(q, key=f"quick_{q}"):
            st.session_state.panel_messages.append({"role": "user", "content": q})
            st.rerun()

st.divider()

# --- Chat history ---
chat_container = st.container()
with chat_container:
    for msg in st.session_state.panel_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

# --- Send message ---
def build_system_prompt(context: str) -> str:
    base = (
        "You are Stelic Copilot, an expert AI assistant for construction project controls. "
        "You specialize in Primavera P6 schedules, project risk, milestone tracking, and schedule analysis. "
        "Be concise, professional, and cite data when available. "
        "If no schedule is loaded, answer general construction/project controls questions helpfully."
    )
    if context:
        base += f"\n\nCONTEXT PROVIDED BY USER:\n{context}"
    return base

def query_copilot(user_input: str, history: list, context: str, image_payload: dict = None) -> str:
    client = get_client()
    if not client:
        return "⚠️ No API key configured. Add OPENAI_API_KEY in Streamlit secrets or Settings."

    system_prompt = build_system_prompt(context)
    trimmed = history[-10:] if len(history) > 10 else history
    messages = [{"role": "system", "content": system_prompt}] + trimmed

    if image_payload:
        # Vision message
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_input},
                {"type": "image_url", "image_url": {
                    "url": f"data:{image_payload['mime']};base64,{image_payload['b64']}"
                }}
            ]
        })
        model = "gpt-4o"
    else:
        messages.append({"role": "user", "content": user_input})
        model = config.get("ai_model", "gpt-4-turbo")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ AI Error: {str(e)}"

if prompt := st.chat_input("Ask about your project, schedule, or paste data..."):
    st.session_state.panel_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner(""):
            history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.panel_messages[:-1]]
            response = query_copilot(
                prompt,
                history,
                st.session_state.panel_context,
                st.session_state.panel_image_payload
            )
            # Clear image after use (one-shot)
            if st.session_state.panel_image_payload:
                st.session_state.panel_image_payload = None
            st.markdown(response)

    st.session_state.panel_messages.append({"role": "assistant", "content": response})
    st.rerun()

# --- Clear chat ---
if st.session_state.panel_messages:
    if st.button("🗑 Clear chat", key="clear_chat"):
        st.session_state.panel_messages = []
        st.rerun()
