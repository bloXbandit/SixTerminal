import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from parser import P6Parser
from analyzer import ScheduleAnalyzer
from dashboard import DashboardGenerator
from copilot import ScheduleCopilot
from diff_engine import DiffEngine
from config import config
import os
import tempfile
import time
from functools import lru_cache
import hashlib
import pickle
import re

# Page Config
st.set_page_config(
    page_title="Stelic Insights",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
    
    /* Global font styling */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Headers with modern font */
    h1, h2, h3 {
        font-family: 'Inter', sans-serif;
        font-weight: 700;
        letter-spacing: -0.02em;
    }
    
    h1 {
        font-size: 2.5rem !important;
        color: #60a5fa !important;
        margin-bottom: 0.5rem !important;
        font-weight: 800 !important;
    }
    
    h2 {
        font-size: 1.8rem !important;
        color: #e2e8f0 !important;
        margin-top: 0.5rem !important;
        margin-bottom: 0.5rem !important;
        padding-bottom: 0.3rem;
        border-bottom: 2px solid #475569;
    }
    
    h3 {
        font-size: 1.2rem !important;
        color: #cbd5e1 !important;
        margin-top: 0.8rem !important;
        margin-bottom: 0.5rem !important;
    }
    
    /* Section dividers */
    hr {
        margin: 1rem 0 !important;
        border: none !important;
        height: 1px !important;
        background: linear-gradient(90deg, transparent, #475569, transparent) !important;
    }
    
    /* Metric cards */
    [data-testid="stMetricValue"] {
        font-size: 2.2rem !important;
        font-weight: 700 !important;
        font-family: 'JetBrains Mono', monospace !important;
    }
    
    [data-testid="stMetricLabel"] {
        font-size: 0.9rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #cbd5e1 !important;
    }
    
    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
        background-color: transparent;
        padding: 8px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
    }
    
    .stTabs [data-baseweb="tab"] {
        padding: 12px 24px;
        font-weight: 600;
        border-radius: 8px;
        transition: all 0.3s ease;
        color: #0f172a;
        background-color: transparent;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background-color: #f1f5f9;
    }
    
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background-color: #e2e8f0;
        color: #0f172a;
    }
    
    /* Cards and containers */
    .element-container {
        margin-bottom: 1rem;
    }
    
    /* Dataframe styling */
    [data-testid="stDataFrame"] {
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    
    /* Button styling */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    
    /* Section spacing */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# Session State Initialization
if "messages" not in st.session_state:
    st.session_state.messages = []
if "parser_cache" not in st.session_state:
    st.session_state.parser_cache = {}
if "comparison_file" not in st.session_state:
    st.session_state.comparison_file = None


# Create persistent storage directory
PERSISTENT_DIR = os.path.join(os.path.dirname(__file__), ".persistent_data")
if not os.path.exists(PERSISTENT_DIR):
    os.makedirs(PERSISTENT_DIR)

def save_uploaded_file(file_bytes, filename):
    """Save uploaded file to persistent storage"""
    file_hash = hashlib.md5(file_bytes).hexdigest()
    file_path = os.path.join(PERSISTENT_DIR, f"{file_hash}.xer")
    
    # Save file if not already saved
    if not os.path.exists(file_path):
        with open(file_path, 'wb') as f:
            f.write(file_bytes)
    
    # Save metadata
    meta_path = os.path.join(PERSISTENT_DIR, "last_upload.pkl")
    with open(meta_path, 'wb') as f:
        pickle.dump({'filename': filename, 'hash': file_hash, 'path': file_path}, f)
    
    return file_path

def load_last_uploaded_file():
    """Load the last uploaded file from persistent storage"""
    meta_path = os.path.join(PERSISTENT_DIR, "last_upload.pkl")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, 'rb') as f:
                meta = pickle.load(f)
            if os.path.exists(meta['path']):
                return meta
        except:
            pass
    return None

@st.cache_resource(ttl=3600)
def load_and_parse_xer(file_bytes, filename):
    """Cached XER parsing for performance"""
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".xer")
    tfile.write(file_bytes)
    tfile.close()
    
    parser = P6Parser(tfile.name)
    analyzer = ScheduleAnalyzer(parser)
    
    os.unlink(tfile.name)  # Clean up temp file
    return parser, analyzer

def main():
    # --- SIDEBAR ---
    with st.sidebar:
        st.title("Stelic Insights 🏗️")
        st.caption("P6 Stairway Tracker & AI Copilot")
        
        # Navigation
        page = st.radio("Navigate", ["📊 Dashboard", "⚙️ Settings", "📖 Help"], label_visibility="collapsed")
        
        st.divider()
        
        if page == "📊 Dashboard":
            # Try to load last uploaded file on startup
            if 'initialized' not in st.session_state:
                st.session_state.initialized = True
                last_file = load_last_uploaded_file()
                if last_file:
                    try:
                        with open(last_file['path'], 'rb') as f:
                            file_bytes = f.read()
                        st.session_state.parser, st.session_state.analyzer = load_and_parse_xer(
                            file_bytes, last_file['filename']
                        )
                        st.session_state.current_file = last_file['filename']
                    except:
                        pass
            
            uploaded_file = st.file_uploader("Upload Schedule (.xer)", type="xer", key="main_file")
            
            # Show currently loaded file if exists
            if 'current_file' in st.session_state and st.session_state.current_file:
                st.info(f"📂 Current: {st.session_state.current_file}")
            
            if uploaded_file:
                # Save file to persistent storage
                file_bytes = uploaded_file.getvalue()
                save_uploaded_file(file_bytes, uploaded_file.name)
                
                # Load parser and analyzer into session state for AI Copilot
                if 'current_file' not in st.session_state or st.session_state.current_file != uploaded_file.name:
                    with st.spinner("Loading schedule..."):
                        st.session_state.parser, st.session_state.analyzer = load_and_parse_xer(
                            file_bytes, uploaded_file.name
                        )
                        st.session_state.current_file = uploaded_file.name
                
                st.success("✅ File Loaded & Saved")
                
                # Quick Actions
                st.subheader("Quick Actions")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("📊 Generate Excel", use_container_width=True):
                        with st.spinner("Generating..."):
                            parser, analyzer = load_and_parse_xer(uploaded_file.getvalue(), uploaded_file.name)
                            output_path = f"dashboard_{uploaded_file.name}.xlsx"
                            gen = DashboardGenerator(analyzer, output_path)
                            gen.generate()
                            
                            with open(output_path, "rb") as f:
                                st.download_button(
                                    label="⬇️ Download",
                                    data=f,
                                    file_name=output_path,
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    use_container_width=True
                                )
                            os.unlink(output_path)
                
                with col2:
                    if st.button("🔄 Refresh", use_container_width=True):
                        st.cache_data.clear()
                        st.rerun()
        
        elif page == "⚙️ Settings":
            render_settings_page()
        
        elif page == "📖 Help":
            render_help_page()

    # --- MAIN CONTENT ---
    if page == "📊 Dashboard":
        # Check if we have parser/analyzer in session state (from upload or auto-load)
        has_data = (hasattr(st.session_state, 'parser') and st.session_state.parser is not None and
                    hasattr(st.session_state, 'analyzer') and st.session_state.analyzer is not None)
        
        if has_data:
            # Create a mock uploaded file object for render_dashboard if needed
            if 'uploaded_file' in locals() and uploaded_file:
                render_dashboard(uploaded_file)
            else:
                # Dashboard exists from auto-loaded file
                class MockUploadedFile:
                    def __init__(self, name):
                        self.name = name
                    def getvalue(self):
                        # Return cached file bytes if available
                        last_file = load_last_uploaded_file()
                        if last_file and os.path.exists(last_file['path']):
                            with open(last_file['path'], 'rb') as f:
                                return f.read()
                        return b''
                
                mock_file = MockUploadedFile(st.session_state.get('current_file', 'schedule.xer'))
                render_dashboard(mock_file)
        else:
            render_landing_page()
    elif page == "⚙️ Settings":
        pass  # Already rendered in sidebar
    elif page == "📖 Help":
        pass  # Already rendered in sidebar
    
    # --- AI CHAT CONTAINER (Bottom of page, persistent) ---
    render_bottom_chat()

def render_bottom_chat():
    """Persistent AI chat container at bottom of page"""

    def get_local_copilot_response(user_text: str, current_view: str) -> str | None:
        if not user_text:
            return None

        t = user_text.strip().lower()
        # Deterministic UI-context questions (avoid burning tokens + avoid model confusion)
        if re.search(r"\b(what\s+page|what\s+tab|where\s+am\s+i|which\s+page|which\s+tab)\b", t):
            return f"You're currently on: {current_view}."

        return None
    
    # Check if schedule is loaded
    has_parser = hasattr(st.session_state, 'parser') and st.session_state.parser is not None
    has_analyzer = hasattr(st.session_state, 'analyzer') and st.session_state.analyzer is not None
    
    # Initialize chat expanded state if not set
    if 'chat_expanded' not in st.session_state:
        st.session_state.chat_expanded = False 

    # Handle pending prompt from minimized state
    if 'pending_prompt' in st.session_state and st.session_state.pending_prompt:
        prompt = st.session_state.pending_prompt
        del st.session_state.pending_prompt
        
        # Add to history
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Get response
        if not has_parser or not has_analyzer:
             st.session_state.messages.append({"role": "assistant", "content": "Please upload a schedule file first so I can assist you."})
        else:
            try:
                # Check API key
                api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
                if not api_key:
                     st.session_state.messages.append({"role": "assistant", "content": "⚠️ Please configure your OpenAI API key in Settings."})
                else:
                    copilot = ScheduleCopilot(st.session_state.parser, st.session_state.analyzer)
                    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
                    current_view = st.session_state.get('current_view', 'Dashboard')

                    local_response = get_local_copilot_response(prompt, current_view)
                    if local_response is not None:
                        response = local_response
                    else:
                        with st.spinner("Thinking..."):
                            response = copilot.query(prompt, history, current_view=current_view)
                    st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                st.session_state.messages.append({"role": "assistant", "content": f"❌ Error: {str(e)}"})
        
        # Force rerun to show result
        st.rerun()

    # CSS for the chat container
    st.markdown("""
    <style>
    .chat-container {
        width: 100%;
        max-width: 1200px;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1rem;
        margin: 1rem auto;
        box-shadow: 0 4px 20px rgba(15, 23, 42, 0.08);
    }
    
    .chat-history-scroll {
        max-height: 400px;
        overflow-y: auto;
        padding: 0.5rem;
        margin-bottom: 1rem;
    }
    
    .chat-title {
        font-family: sans-serif;
        font-size: 1.1rem;
        font-weight: 700;
        color: #2563eb;
        display: flex;
        align-items: center;
        gap: 8px;
        white-space: nowrap;
    }
    
    .chat-message {
        padding: 10px 14px;
        border-radius: 8px;
        margin-bottom: 8px;
        font-size: 0.95rem;
        line-height: 1.5;
    }
    
    .user-message {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        color: #0f172a;
        margin-left: 2rem;
    }
    
    .assistant-message {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        color: #334155;
        margin-right: 2rem;
    }
    
    /* Ensure inputs are visible */
    input[type="text"] {
        color: #0f172a !important;
        background-color: #ffffff !important; 
        border: 1px solid #cbd5e1 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Create container (no longer fixed to bottom)
    with st.container():
        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        
        # --- COLLAPSED STATE ---
        if not st.session_state.chat_expanded:
            c1, c2 = st.columns([10, 1], gap="small")
            with c1:
                st.markdown('<div class="chat-title">⚡ Stelic Copilot</div>', unsafe_allow_html=True)
            with c2:
                if st.button("▲", key="expand_btn", use_container_width=True):
                    st.session_state.chat_expanded = True
                    st.rerun()

            st.markdown("<div style='height: 0.35rem;'></div>", unsafe_allow_html=True)

            def on_submit():
                st.session_state.pending_prompt = st.session_state.mini_input
                st.session_state.chat_expanded = True
                st.session_state.mini_input = "" # Clear input

            st.text_input(
                "Ask Stelic...",
                key="mini_input",
                placeholder="Type your question here...",
                label_visibility="collapsed",
                on_change=on_submit
            )

        # --- EXPANDED STATE ---
        else:
            # Header
            h1, h2, h3 = st.columns([6, 3, 1])
            with h1:
                st.markdown('<div class="chat-title">⚡ Stelic Copilot</div>', unsafe_allow_html=True)
            with h2:
                status_text = "System Active" if has_parser and has_analyzer else "Waiting for Schedule"
                st.caption(f"● {status_text}")
            with h3:
                if st.button("▼", key="collapse_btn", use_container_width=True):
                    st.session_state.chat_expanded = False
                    st.rerun()
            
            st.divider()
            
            # Chat Area
            if not has_parser or not has_analyzer:
                st.info("📂 Upload a .xer schedule file to activate 6ix Copilot")
            else:
                chat_col, action_col = st.columns([3, 1])
                
                with action_col:
                    st.caption("Quick Actions")
                    if st.button("🔥 Risks", use_container_width=True):
                        st.session_state.pending_prompt = "What are the critical risks?"
                        st.rerun()
                    if st.button("📊 Status", use_container_width=True):
                        st.session_state.pending_prompt = "Project status summary?"
                        st.rerun()
                    if st.button("🔄 Reset", use_container_width=True):
                        st.session_state.messages = []
                        st.rerun()
                
                with chat_col:
                    # Welcome Message Logic
                    if not st.session_state.messages:
                        st.markdown("""
                            <div style="text-align: center; padding: 20px; color: #94a3b8;">
                                <div style="font-size: 40px;">👷</div>
                                <h3>Hi! I'm 6ix Copilot.</h3>
                                <p>Ask me anything about your schedule.</p>
                            </div>
                        """, unsafe_allow_html=True)
                    else:
                        # Scrollable chat history - show ALL messages
                        st.markdown('<div class="chat-history-scroll">', unsafe_allow_html=True)
                        for msg in st.session_state.messages:
                            role_class = "user-message" if msg["role"] == "user" else "assistant-message"
                            icon = "👤" if msg["role"] == "user" else "⚡"
                            st.markdown(f"""
                                <div class="chat-message {role_class}">
                                    <strong>{icon}</strong> {msg['content']}
                                </div>
                            """, unsafe_allow_html=True)
                        st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Main Input
                    def on_main_submit():
                        st.session_state.pending_prompt = st.session_state.main_input
                        st.session_state.main_input = ""

                    st.text_input("Message...", key="main_input", 
                                 placeholder="Ask a question...", 
                                 label_visibility="collapsed",
                                 on_change=on_main_submit)

        st.markdown('</div>', unsafe_allow_html=True)



def render_landing_page():
    # Logo and title with tighter spacing
    col1, col2 = st.columns([1, 5], gap="small")
    with col1:
        # Display logo
        logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
        if os.path.exists(logo_path):
            st.image(logo_path, width=100)
        else:
            st.markdown("🏗️", unsafe_allow_html=True)
    with col2:
        st.markdown("<h1 style='margin-top: 20px; margin-bottom: 5px;'>Stelic Insights</h1>", unsafe_allow_html=True)
        st.markdown("<p style='font-size: 14px; color: #888; margin-top: 0;'>Copilot interface for Primavera P6 files</p>", unsafe_allow_html=True)
    
    st.markdown("""
    Upload your **.xer** file in the sidebar to begin analyzing your schedule.
    
    ## Features
    
    **📊 Stairway Visualization**  
    Track milestone progression with visual baseline vs forecast comparison.
    
    **🧠 AI Copilot**  
    Ask natural language questions about your schedule: *"Why is the foundation delayed?"*
    
    **⚡ Auto-Analysis**  
    Instant critical path identification and variance detection.
    
    **🔍 Change Detection**  
    Compare two schedule versions to track slips and changes.
    
    **📑 Excel Exports**  
    Generate stakeholder-ready dashboards with professional formatting.
    
    ## Quick Start
    1. Upload a .xer file in the sidebar
    2. Explore the dashboard tabs
    3. Generate Excel reports
    4. Compare schedule versions
    5. Ask the AI Copilot questions
    """)
    
    # Stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Supported Formats", "XER")
    with col2:
        st.metric("Analysis Speed", "<30s")
    with col3:
        st.metric("AI Models", "GPT-5.2")

def render_dashboard(uploaded_file):
    try:
        # Load with caching
        parser, analyzer = load_and_parse_xer(uploaded_file.getvalue(), uploaded_file.name)
        
        # Store in session state for sidebar access
        st.session_state.parser = parser
        st.session_state.analyzer = analyzer
        
        dashboard_view = st.radio(
            "Dashboard View",
            [
                "🚀 Executive Summary",
                "📈 Stairway Visuals",
                "📦 Material & Procurement",
                "📅 Current Month Focus",
                "🔍 Compare Schedules",
                "📋 Data Tables"
            ],
            horizontal=True,
            label_visibility="collapsed",
            key="dashboard_view"
        )
        st.session_state.current_view = dashboard_view
        
        # Debug: Check analyzer state
        if analyzer.df_main is None or analyzer.df_main.empty:
            st.warning("⚠️ No activities found in XER file. The file may be empty or have parsing issues.")
            st.info(f"Debug: Parser has {len(parser.get_activities())} raw activities")
            if not parser.get_activities().empty:
                st.write("Available columns:", parser.get_activities().columns.tolist())
        
        stats = analyzer.get_dashboard_summary()
        
        # Ensure stats has all required keys
        if not stats or 'total_activities' not in stats:
            stats = {
                "data_date": "N/A",
                "total_activities": 0,
                "critical_activities": 0,
                "slipping_activities": 0,
                "percent_critical": 0
            }
        
        if dashboard_view == "🚀 Executive Summary":
            render_executive_summary(analyzer, stats)
        elif dashboard_view == "📈 Stairway Visuals":
            render_stairway_visuals(analyzer)
        elif dashboard_view == "📦 Material & Procurement":
            render_procurement_tracker(analyzer)
        elif dashboard_view == "📅 Current Month Focus":
            render_current_month_focus(analyzer)
        elif dashboard_view == "🔍 Compare Schedules":
            render_compare_schedules(parser, analyzer)
        elif dashboard_view == "📋 Data Tables":
            render_data_tables(analyzer)
        
    
    except Exception as e:
        st.error(f"❌ Error processing XER: {str(e)}")
        st.write("Ensure your .xer file is a valid P6 export.")
        if st.button("Show Debug Info"):
            st.exception(e)

def render_executive_summary(analyzer, stats):
    # Header with icon
    st.markdown("## <span style='color: #f97316;'>📊 Project Health Dashboard</span>", unsafe_allow_html=True)
    st.divider()
    
    # Get project duration metrics
    duration_info = analyzer.get_project_duration()
    
    # KPI Metrics
    st.markdown("### Key Performance Indicators")

    kpi_pad_l, kpi_main, kpi_pad_r = st.columns([1, 10, 1], gap="small")
    with kpi_main:
        col1, col2, col3, col4 = st.columns(4, gap="small")
        col1.metric("Total Activities", stats['total_activities'])
        col2.metric(
            "Critical Activities",
            stats['critical_activities'],
            delta=f"{stats['percent_critical']}%",
            delta_color="inverse"
        )
        col3.metric("Slipping (>5 days)", stats['slipping_activities'], delta="-Risk")
        col4.metric("Data Date", stats['data_date'])

        col5, col6, col7, col8 = st.columns(4, gap="small")
        col5.metric("📅 Project Duration", f"{duration_info['duration_days']:,} days")
        col6.metric(
            "✅ Duration % Complete",
            f"{duration_info['percent_complete']}%",
            delta=f"{duration_info['percent_complete']}%"
        )
        col7.metric("🚀 Project Start", duration_info['project_start'] if duration_info['project_start'] else "N/A")
        col8.metric("🏁 Project Finish", duration_info['project_finish'] if duration_info['project_finish'] else "N/A")
    
    st.divider()
    
    # Critical Path Timeline
    st.markdown("### 🎯 Top 10 Critical Path Drivers")
    crit_df = analyzer.get_critical_path().head(10)
    
    if not crit_df.empty:
        # Add task_code to display labels
        if 'task_code' in crit_df.columns:
            crit_df['display_name'] = crit_df['task_name'] + ' (' + crit_df['task_code'].astype(str) + ')'
        else:
            crit_df['display_name'] = crit_df['task_name']
        
        fig = px.timeline(
            crit_df, 
            x_start="current_start", 
            x_end="current_finish", 
            y="display_name",
            color="total_float_hr_cnt",
            title="Critical Path Activities",
            labels={"total_float_hr_cnt": "Total Float (Hrs)", "display_name": "Activity"},
            hover_data=['task_code'] if 'task_code' in crit_df.columns else None
        )
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(
            height=380,
            margin=dict(t=50, b=10, l=10, r=10)
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Show table with Activity Details
        st.subheader("Critical Path Details")
        display_cols = ['task_code', 'task_name', 'current_start', 'current_finish']
        available_cols = [col for col in display_cols if col in crit_df.columns]
        
        # Format dates as MM/DD/YYYY
        display_df = crit_df[available_cols].copy()
        for col in ['current_start', 'current_finish']:
            if col in display_df.columns:
                display_df[col] = pd.to_datetime(display_df[col]).dt.strftime('%m/%d/%Y')
        
        st.dataframe(display_df, use_container_width=True, height=300)
    else:
        st.info("✅ No critical path activities found - project has positive float!")
    
    st.divider()
    
    # Health Indicators
    st.markdown("### 🏥 Schedule Health Indicators")
    col1, col2 = st.columns(2)
    
    with col1:
        if stats['percent_critical'] > 20:
            st.error("⚠️ **HIGH RISK**: Critical path saturation > 20%")
        elif stats['percent_critical'] > 10:
            st.warning("⚠️ **MODERATE RISK**: Critical path saturation > 10%")
        else:
            st.success("✅ **HEALTHY**: Critical path saturation < 10%")
    
    with col2:
        if stats['slipping_activities'] > stats['total_activities'] * 0.15:
            st.error("⚠️ **HIGH SLIPPAGE**: >15% of activities slipping")
        elif stats['slipping_activities'] > 0:
            st.warning(f"⚠️ **MODERATE SLIPPAGE**: {stats['slipping_activities']} activities slipping")
        else:
            st.success("✅ **ON TRACK**: No significant slippage detected")
    
    st.divider()
    
    # Schedule Log Metrics (P6 Schedule Health)
    st.markdown("### 📊 P6 Schedule Log Metrics")
    
    health_metrics = analyzer.get_schedule_health_metrics()
    
    if health_metrics:
        col1, col2, col3, col4 = st.columns(4)
        
        col1.metric("🔗 Relationships", health_metrics.get('total_relationships', 0))
        col2.metric("⛓️ Constraints", health_metrics.get('total_constraints', 0))
        col3.metric("🔓 Open Starts", health_metrics.get('no_predecessors', 0), 
                   help="Activities with no predecessors")
        col4.metric("🔓 Open Ends", health_metrics.get('no_successors', 0),
                   help="Activities with no successors")
        
        # Detailed breakdown in expander
        with st.expander("📝 View Detailed Schedule Metrics"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Constraint Types:**")
                constraint_breakdown = health_metrics.get('constraint_breakdown', {})
                if constraint_breakdown:
                    for cstr, count in sorted(constraint_breakdown.items(), key=lambda x: x[1], reverse=True):
                        cstr_label = {
                            'CS_ALAP': 'As Late As Possible',
                            'CS_ASAP': 'As Soon As Possible',
                            'CS_MSOA': 'Must Start On or After',
                            'CS_MSOB': 'Must Start On or Before',
                            'CS_MEOA': 'Must Finish On or After',
                            'CS_MEOB': 'Must Finish On or Before',
                            'CS_FNLT': 'Finish No Later Than',
                            'CS_FNST': 'Finish No Sooner Than',
                            'CS_MANDSTART': 'Mandatory Start',
                            'CS_MANDFINISH': 'Mandatory Finish'
                        }.get(cstr, cstr)
                        st.write(f"- {cstr_label} ({cstr}): {count}")
                else:
                    st.write("No constraints")
            
            with col2:
                st.markdown("**Relationship Types:**")
                rel_breakdown = health_metrics.get('relationship_breakdown', {})
                if rel_breakdown:
                    for rel, count in sorted(rel_breakdown.items(), key=lambda x: x[1], reverse=True):
                        rel_label = {
                            'PR_FS': 'Finish-to-Start',
                            'PR_SS': 'Start-to-Start',
                            'PR_FF': 'Finish-to-Finish',
                            'PR_SF': 'Start-to-Finish'
                        }.get(rel, rel)
                        st.write(f"- {rel_label}: {count}")
                else:
                    st.write("No relationships")
            
            # Warnings for schedule quality issues
            st.markdown("**Schedule Quality Checks:**")
            if health_metrics.get('no_predecessors', 0) > 1:
                st.warning(f"⚠️ {health_metrics['no_predecessors']} activities have no predecessors (may indicate logic gaps)")
            if health_metrics.get('no_successors', 0) > 1:
                st.warning(f"⚠️ {health_metrics['no_successors']} activities have no successors (may indicate logic gaps)")
            if health_metrics.get('total_constraints', 0) > stats['total_activities'] * 0.05:
                st.warning(f"⚠️ {health_metrics['total_constraints']} constraints (>{5}% of activities - may over-constrain schedule)")
            if not health_metrics.get('no_predecessors', 0) > 1 and not health_metrics.get('no_successors', 0) > 1:
                st.success("✅ Schedule logic appears well-connected")

def render_stairway_visuals(analyzer):
    st.header("Milestone Stairway Tracker")
    
    milestones = analyzer.get_milestones()
    
    if not milestones.empty:
        plot_milestones = milestones.copy()
        date_cols = [c for c in ['current_finish', 'target_end_date'] if c in plot_milestones.columns]
        if date_cols:
            plot_milestones = plot_milestones[plot_milestones[date_cols].notna().any(axis=1)]

        if plot_milestones.empty:
            st.warning("⚠️ Milestones found but no milestone dates available to plot.")
            return

        # Add task_code to milestone display names
        if 'task_code' in plot_milestones.columns:
            plot_milestones['display_name'] = plot_milestones['task_name'] + ' (' + plot_milestones['task_code'].astype(str) + ')'
        else:
            plot_milestones['display_name'] = plot_milestones['task_name']
        
        # --- SVG Stairway Chart ---
        import numpy as np

        # Sort milestones by forecast finish date
        plot_milestones = plot_milestones.copy()
        plot_milestones['_fc_dt'] = pd.to_datetime(plot_milestones['current_finish'], errors='coerce')
        plot_milestones['_bl_dt'] = pd.to_datetime(plot_milestones['target_end_date'], errors='coerce')
        plot_milestones = plot_milestones.dropna(subset=['_fc_dt']).sort_values('_fc_dt').reset_index(drop=True)

        n = len(plot_milestones)
        if n == 0:
            st.warning("No milestone dates available.")
        else:
            # Layout constants
            LEFT_PAD = 200   # space for milestone labels
            RIGHT_PAD = 20
            TOP_PAD = 20
            BOTTOM_PAD = 50  # space for x-axis date labels
            ROW_H = 28       # vertical step per milestone
            SVG_W = 900
            chart_w = SVG_W - LEFT_PAD - RIGHT_PAD
            chart_h = n * ROW_H
            SVG_H = TOP_PAD + chart_h + BOTTOM_PAD

            # Date range for x-axis
            all_dates = pd.concat([plot_milestones['_fc_dt'], plot_milestones['_bl_dt'].dropna()])
            date_min = all_dates.min()
            date_max = all_dates.max()
            span = max((date_max - date_min).days, 1)
            # Add 5% padding on each side
            pad_days = max(int(span * 0.05), 10)
            x_min = date_min - pd.Timedelta(days=pad_days)
            x_max = date_max + pd.Timedelta(days=pad_days)
            total_days = (x_max - x_min).days

            def date_to_x(d):
                if pd.isnull(d):
                    return None
                return LEFT_PAD + chart_w * (d - x_min).days / total_days

            def row_to_y(i):
                return TOP_PAD + i * ROW_H + ROW_H // 2

            svg_parts = []
            svg_parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" height="{SVG_H}" style="background:#fff;font-family:sans-serif">')

            # Grid lines (light vertical)
            # Generate ~6 evenly spaced tick dates
            tick_count = 6
            tick_interval = total_days / tick_count
            for ti in range(tick_count + 1):
                tick_date = x_min + pd.Timedelta(days=int(ti * tick_interval))
                tx = date_to_x(tick_date)
                svg_parts.append(f'<line x1="{tx:.1f}" y1="{TOP_PAD}" x2="{tx:.1f}" y2="{TOP_PAD + chart_h}" stroke="#e9ecef" stroke-width="1"/>')
                label = tick_date.strftime('%b %y')
                svg_parts.append(f'<text x="{tx:.1f}" y="{TOP_PAD + chart_h + 14}" text-anchor="middle" font-size="10" fill="#6c757d">{label}</text>')

            # Stairway connecting line (forecast dots stepped)
            step_points = []
            for i, row in plot_milestones.iterrows():
                fx = date_to_x(row['_fc_dt'])
                fy = row_to_y(i)
                if fx is not None:
                    step_points.append((fx, fy))

            if len(step_points) > 1:
                path_d = f"M {step_points[0][0]:.1f} {step_points[0][1]:.1f}"
                for k in range(1, len(step_points)):
                    px0, py0 = step_points[k-1]
                    px1, py1 = step_points[k]
                    # step: go right then down
                    path_d += f" L {px1:.1f} {py0:.1f} L {px1:.1f} {py1:.1f}"
                svg_parts.append(f'<path d="{path_d}" fill="none" stroke="#adb5bd" stroke-width="1.5" stroke-dasharray="4 2"/>')

            # Per-milestone rows
            for i, row in plot_milestones.iterrows():
                fy = row_to_y(i)
                fx = date_to_x(row['_fc_dt'])
                bx = date_to_x(row['_bl_dt'])

                is_complete = (pd.notnull(row.get('act_end_date')) if 'act_end_date' in plot_milestones.columns else False) or \
                              (row.get('complete_pct', 0) >= 100 if 'complete_pct' in plot_milestones.columns else False)
                fc_color = '#28a745' if is_complete else '#4169E1'

                v = row.get('variance_days', 0) or 0
                vc = '#dc3545' if v > 0 else '#28a745' if v < 0 else '#6c757d'
                vt = f"+{int(v)}d" if v > 0 else f"{int(v)}d" if v < 0 else "0d"

                # Horizontal row line (light)
                svg_parts.append(f'<line x1="{LEFT_PAD}" y1="{fy}" x2="{SVG_W - RIGHT_PAD}" y2="{fy}" stroke="#f1f3f5" stroke-width="1"/>')

                # Milestone label (left side)
                label = str(row['display_name'])
                if len(label) > 32:
                    label = label[:30] + '…'
                svg_parts.append(f'<text x="{LEFT_PAD - 6}" y="{fy + 4}" text-anchor="end" font-size="11" fill="#212529">{label}</text>')

                # Baseline diamond (grey outline)
                if bx is not None:
                    d = 6
                    svg_parts.append(f'<polygon points="{bx:.1f},{fy-d} {bx+d:.1f},{fy} {bx:.1f},{fy+d} {bx-d:.1f},{fy}" fill="none" stroke="#6c757d" stroke-width="1.5"/>')

                # Connector line between baseline and forecast
                if bx is not None and fx is not None and abs(fx - bx) > 2:
                    svg_parts.append(f'<line x1="{bx:.1f}" y1="{fy}" x2="{fx:.1f}" y2="{fy}" stroke="#dee2e6" stroke-width="1" stroke-dasharray="3 2"/>')

                # Forecast diamond (filled)
                if fx is not None:
                    d = 6
                    svg_parts.append(f'<polygon points="{fx:.1f},{fy-d} {fx+d:.1f},{fy} {fx:.1f},{fy+d} {fx-d:.1f},{fy}" fill="{fc_color}" stroke="{fc_color}" stroke-width="1"/>')
                    # Forecast date label above diamond
                    fd_label = row['_fc_dt'].strftime('%b %y')
                    svg_parts.append(f'<text x="{fx:.1f}" y="{fy - 9}" text-anchor="middle" font-size="9" fill="{fc_color}">{fd_label}</text>')

                # Variance badge (right side)
                if v != 0:
                    vx = SVG_W - RIGHT_PAD - 28
                    svg_parts.append(f'<text x="{vx}" y="{fy + 4}" text-anchor="middle" font-size="10" font-weight="bold" fill="{vc}">{vt}</text>')

            # X-axis line
            svg_parts.append(f'<line x1="{LEFT_PAD}" y1="{TOP_PAD + chart_h}" x2="{SVG_W - RIGHT_PAD}" y2="{TOP_PAD + chart_h}" stroke="#dee2e6" stroke-width="1.5"/>')

            # Legend
            lx = LEFT_PAD
            ly = SVG_H - 12
            svg_parts.append(f'<polygon points="{lx},{ly-5} {lx+5},{ly} {lx},{ly+5} {lx-5},{ly}" fill="none" stroke="#6c757d" stroke-width="1.5"/>')
            svg_parts.append(f'<text x="{lx+8}" y="{ly+4}" font-size="10" fill="#6c757d">Baseline</text>')
            svg_parts.append(f'<polygon points="{lx+75},{ly-5} {lx+80},{ly} {lx+75},{ly+5} {lx+70},{ly}" fill="#4169E1" stroke="#4169E1" stroke-width="1"/>')
            svg_parts.append(f'<text x="{lx+83}" y="{ly+4}" font-size="10" fill="#4169E1">Forecast</text>')
            svg_parts.append(f'<polygon points="{lx+150},{ly-5} {lx+155},{ly} {lx+150},{ly+5} {lx+145},{ly}" fill="#28a745" stroke="#28a745" stroke-width="1"/>')
            svg_parts.append(f'<text x="{lx+158}" y="{ly+4}" font-size="10" fill="#28a745">Complete</text>')

            svg_parts.append('</svg>')

            svg_html = '\n'.join(svg_parts)
            st.markdown(f'<div style="overflow-x:auto">{svg_html}</div>', unsafe_allow_html=True)
        
        # Variance Analysis
        st.subheader("Milestone Variance Analysis")
        
        # Color code the dataframe
        def highlight_variance(val):
            if pd.isna(val):
                return ''
            if val > 10:
                return 'background-color: #ffcccc'
            elif val > 0:
                return 'background-color: #ffffcc'
            else:
                return 'background-color: #ccffcc'
        
        # Include Activity Code for easier identification
        display_cols = ['task_code', 'task_name', 'target_end_date', 'current_finish', 'variance_days']
        available_cols = [col for col in display_cols if col in milestones.columns]
        
        # Format dates as MM/DD/YYYY
        display_milestones = milestones[available_cols].copy()
        for col in ['target_end_date', 'current_finish']:
            if col in display_milestones.columns:
                display_milestones[col] = pd.to_datetime(display_milestones[col]).dt.strftime('%m/%d/%Y')
        
        styled_df = display_milestones.style.applymap(
            highlight_variance, subset=['variance_days'] if 'variance_days' in available_cols else []
        )
        
        st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
        st.subheader("Detailed Milestone Data")
        st.dataframe(styled_df, use_container_width=True, height=350)
    else:
        st.warning("⚠️ No milestones found in schedule. Check your activity types.")

def render_procurement_tracker(analyzer):
    """
    Render Material & Procurement Tracker tab
    Shows auto-detected procurement items with manual add/remove capability
    """
    st.header("📦 Material & Procurement Tracker")
    
    st.markdown("""
    Track major material orders, fabrication, and deliveries. Items are auto-detected based on:
    - Task codes: FAB-, DEL-, PROC-, MAT-, ORD-, PMU-
    - Keywords: structural steel, precast, curtainwall, major equipment
    - Excludes: submittals, approvals, small hardware
    """)
    
    procurement = analyzer.get_procurement_log()
    
    if procurement.empty:
        st.warning("⚠️ No procurement items detected. Upload a schedule with FAB-, DEL-, or PROC- activities.")
        return
    
    # Summary Metrics
    col1, col2, col3, col4 = st.columns(4)
    
    total_items = len(procurement)
    completed = len(procurement[procurement['status_code'] == 'TK_Complete']) if 'status_code' in procurement.columns else 0
    active = len(procurement[procurement['status_code'] == 'TK_Active']) if 'status_code' in procurement.columns else 0
    not_started = len(procurement[procurement['status_code'] == 'TK_NotStart']) if 'status_code' in procurement.columns else 0
    
    col1.metric("Total Procurement Items", total_items)
    col2.metric("✅ Completed", completed)
    col3.metric("🔄 In Progress", active)
    col4.metric("⏳ Not Started", not_started)
    
    st.divider()
    
    # Filter Options
    st.subheader("Filter & Search")
    col1, col2 = st.columns(2)
    
    with col1:
        search_term = st.text_input("🔍 Search by Activity Name or Code", "")
    
    with col2:
        status_filter = st.multiselect(
            "Filter by Status",
            options=['TK_NotStart', 'TK_Active', 'TK_Complete'],
            default=['TK_NotStart', 'TK_Active', 'TK_Complete']
        )
    
    # Apply filters
    filtered_df = procurement.copy()
    
    if search_term:
        mask = (
            filtered_df['task_name'].str.contains(search_term, case=False, na=False) |
            filtered_df['task_code'].str.contains(search_term, case=False, na=False)
        )
        filtered_df = filtered_df[mask]
    
    if 'status_code' in filtered_df.columns and status_filter:
        filtered_df = filtered_df[filtered_df['status_code'].isin(status_filter)]
    
    st.info(f"📊 Showing {len(filtered_df)} of {total_items} procurement items")
    
    st.divider()
    
    # Procurement Timeline Visualization
    st.subheader("Procurement Timeline")
    
    if not filtered_df.empty and 'current_start' in filtered_df.columns and 'current_finish' in filtered_df.columns:
        # Show top 20 items in timeline
        timeline_df = filtered_df.head(20).copy()
        
        fig = px.timeline(
            timeline_df,
            x_start="current_start",
            x_end="current_finish",
            y="task_name",
            color="status_code",
            title="Top 20 Procurement Items Timeline",
            labels={"status_code": "Status"},
            color_discrete_map={
                'TK_NotStart': '#FFA500',
                'TK_Active': '#4169E1',
                'TK_Complete': '#32CD32'
            }
        )
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(height=max(400, len(timeline_df) * 30))
        st.plotly_chart(fig, use_container_width=True)
    
    # Detailed Table with Activity IDs
    st.subheader("Procurement Details")
    
    # Select columns to display
    display_cols = [
        'task_code', 'task_name', 'status_code',
        'current_start', 'current_finish', 'complete_pct'
    ]
    available_cols = [col for col in display_cols if col in filtered_df.columns]
    
    # Format dates as MM/DD/YYYY
    display_procurement = filtered_df[available_cols].copy()
    for col in ['current_start', 'current_finish']:
        if col in display_procurement.columns:
            display_procurement[col] = pd.to_datetime(display_procurement[col]).dt.strftime('%m/%d/%Y')
    
    # Color code by status with better text contrast
    def highlight_status(row):
        if 'status_code' not in row:
            return [''] * len(row)
        
        status = row['status_code']
        if status == 'TK_Complete':
            color = 'background-color: #28a745; color: white'  # Dark green with white text
        elif status == 'TK_Active':
            color = 'background-color: #17a2b8; color: white'  # Dark blue with white text
        elif status == 'TK_NotStart':
            color = 'background-color: #6c757d; color: white'  # Gray with white text
        else:
            color = ''
        
        return [color] * len(row)
    
    styled_df = display_procurement.style.apply(highlight_status, axis=1)
    
    st.dataframe(styled_df, use_container_width=True, height=500)
    
    # Export Option
    st.divider()
    st.subheader("Export Procurement Log")
    
    csv = filtered_df[available_cols].to_csv(index=False)
    st.download_button(
        label="📥 Download as CSV",
        data=csv,
        file_name="procurement_log.csv",
        mime="text/csv"
    )
    
    # Manual Selection Info
    st.info("""
    💡 **Manual Selection**: To add activities not auto-detected, go to the **Data Tables** tab, 
    find the activity, and note its Activity ID. You can then filter for it here using the search box.
    """)

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

def render_current_month_focus(analyzer):
    """
    Render Current Month Focus tab - shows exactly where the project is now
    """
    st.header("📅 Current Month Focus")
    
    st.markdown("""
    **Project snapshot based on data date** - What's happening now, what was just completed, and what's coming next.
    """)
    
    # Get monthly data and metrics
    metrics = analyzer.get_monthly_metrics(days_window=30)
    month_data = analyzer.get_current_month_activities(days_window=30)
    
    last_month = month_data['last_month']
    this_month = month_data['this_month']
    next_month = month_data['next_month']
    
    # --- SUMMARY METRICS ---
    st.subheader("📊 Monthly Overview")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    col1.metric("📅 Data Date", metrics['data_date'])
    col2.metric("✅ Last Month", metrics['last_month_completed'], help="Activities completed in last 30 days")
    col3.metric("🔄 This Month", metrics['this_month_active'], help="Activities active or spanning current period")
    col4.metric("⏭️ Next Month", metrics['next_month_starting'], help="Activities starting in next 30 days")
    col5.metric("🎯 Completion Rate", f"{metrics['completion_rate']}%", 
                delta=f"{metrics['actual_completions']}/{metrics['planned_completions']}")
    
    st.divider()
    
    # --- HEALTH INDICATORS ---
    st.subheader("🚦 Current Status")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if metrics['critical_this_month'] > 0:
            st.warning(f"⚠️ **{metrics['critical_this_month']} Critical Activities** this month")
        else:
            st.success("✅ **No Critical Activities** this month")
    
    with col2:
        if metrics['behind_schedule'] > 0:
            st.error(f"🔴 **{metrics['behind_schedule']} Activities Behind** (started but 0% complete)")
        else:
            st.success("✅ **All Active Activities Progressing**")
    
    st.divider()
    
    # --- MONTHLY TREND CHART ---
    st.subheader("📈 Monthly Activity Trend")
    
    trend_data = pd.DataFrame({
        'Period': ['Last Month\n(Completed)', 'This Month\n(Active)', 'Next Month\n(Starting)'],
        'Count': [metrics['last_month_completed'], metrics['this_month_active'], metrics['next_month_starting']],
        'Color': ['#32CD32', '#4169E1', '#FFA500']
    })
    
    fig_trend = px.bar(
        trend_data,
        x='Period',
        y='Count',
        color='Period',
        title='Activity Distribution by Month',
        color_discrete_sequence=['#32CD32', '#4169E1', '#FFA500'],
        text='Count'
    )
    fig_trend.update_traces(textposition='outside')
    fig_trend.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig_trend, use_container_width=True)
    
    st.divider()
    
    # --- TABBED VIEWS FOR EACH PERIOD ---
    tab1, tab2, tab3 = st.tabs(["✅ Last Month Completions", "🔄 This Month Active", "⏭️ Next Month Starting"])
    
    # TAB 1: LAST MONTH COMPLETIONS
    with tab1:
        st.subheader(f"Activities Completed in Last 30 Days ({len(last_month)} items)")
        
        if not last_month.empty:
            # Timeline chart
            if 'act_start_date' in last_month.columns and 'act_end_date' in last_month.columns:
                timeline_df = last_month.head(20).copy()
                
                fig_last = px.timeline(
                    timeline_df,
                    x_start='act_start_date',
                    x_end='act_end_date',
                    y='task_name',
                    color='complete_pct',
                    title='Top 20 Recently Completed Activities',
                    labels={'complete_pct': '% Complete'},
                    color_continuous_scale='Greens',
                    hover_data=['task_id', 'task_code'] if 'task_id' in timeline_df.columns else ['task_code']
                )
                fig_last.update_yaxes(autorange="reversed")
                fig_last.update_layout(height=max(400, len(timeline_df) * 30))
                st.plotly_chart(fig_last, use_container_width=True)
            
            # Detailed table
            st.subheader("Completion Details")
            display_cols = ['task_id', 'task_code', 'task_name', 'act_start_date', 'act_end_date', 
                           'target_drtn_hr_cnt', 'complete_pct']
            available_cols = [col for col in display_cols if col in last_month.columns]
            
            st.dataframe(last_month[available_cols].head(50), use_container_width=True, height=400)
            
            # Export option
            csv = last_month[available_cols].to_csv(index=False)
            st.download_button(
                label="📥 Download Last Month Completions",
                data=csv,
                file_name="last_month_completions.csv",
                mime="text/csv"
            )
        else:
            st.info("No activities completed in the last 30 days.")
    
    # TAB 2: THIS MONTH ACTIVE
    with tab2:
        st.subheader(f"Activities Active This Month ({len(this_month)} items)")
        
        if not this_month.empty:
            # Filter options
            col1, col2 = st.columns(2)
            
            with col1:
                show_critical_only = st.checkbox("Show Critical Path Only", value=False)
            
            with col2:
                show_behind_only = st.checkbox("Show Behind Schedule Only", value=False)
            
            filtered_this_month = this_month.copy()
            
            if show_critical_only and 'total_float_hr_cnt' in filtered_this_month.columns:
                filtered_this_month = filtered_this_month[filtered_this_month['total_float_hr_cnt'] <= 0]
            
            if show_behind_only and 'complete_pct' in filtered_this_month.columns:
                filtered_this_month = filtered_this_month[
                    (filtered_this_month['status_code'] == 'TK_Active') &
                    (filtered_this_month['complete_pct'] == 0)
                ]
            
            st.info(f"Showing {len(filtered_this_month)} of {len(this_month)} activities")
            
            # Timeline chart with data date line
            if 'current_start' in filtered_this_month.columns and 'current_finish' in filtered_this_month.columns:
                timeline_df = filtered_this_month.head(20).copy()
                
                fig_this = px.timeline(
                    timeline_df,
                    x_start='current_start',
                    x_end='current_finish',
                    y='task_name',
                    color='status_code',
                    title='Top 20 Active Activities',
                    labels={'status_code': 'Status'},
                    color_discrete_map={
                        'TK_Active': '#4169E1',
                        'TK_NotStart': '#FFA500',
                        'TK_Complete': '#32CD32'
                    },
                    hover_data=['task_id', 'task_code', 'complete_pct'] if 'task_id' in timeline_df.columns else ['task_code', 'complete_pct']
                )
                
                # Add vertical line for data date
                data_date = datetime.strptime(metrics['data_date'], '%m/%d/%Y')
                fig_this.add_vline(
                    x=data_date.timestamp() * 1000,
                    line_dash="dash",
                    line_color="red",
                    annotation_text="Data Date",
                    annotation_position="top"
                )
                
                fig_this.update_yaxes(autorange="reversed")
                fig_this.update_layout(height=max(400, len(timeline_df) * 30))
                st.plotly_chart(fig_this, use_container_width=True)
            
            # Detailed table with color coding
            st.subheader("Activity Details")
            display_cols = ['task_id', 'task_code', 'task_name', 'status_code', 'current_start', 
                           'current_finish', 'complete_pct', 'total_float_hr_cnt']
            available_cols = [col for col in display_cols if col in filtered_this_month.columns]
            
            def highlight_status(row):
                colors = []
                for col in row.index:
                    if col == 'complete_pct' and 'status_code' in row:
                        if row['status_code'] == 'TK_Active' and row[col] == 0:
                            colors.append('background-color: #ffcccc')  # Red - behind
                        elif row[col] >= 50:
                            colors.append('background-color: #d4edda')  # Green - progressing
                        else:
                            colors.append('')
                    elif col == 'total_float_hr_cnt':
                        if pd.notna(row[col]) and row[col] <= 0:
                            colors.append('background-color: #fff3cd')  # Yellow - critical
                        else:
                            colors.append('')
                    else:
                        colors.append('')
                return colors
            
            styled_df = filtered_this_month[available_cols].head(50).style.apply(highlight_status, axis=1)
            st.dataframe(styled_df, use_container_width=True, height=400)
            
            # Export option
            csv = filtered_this_month[available_cols].to_csv(index=False)
            st.download_button(
                label="📥 Download This Month Activities",
                data=csv,
                file_name="this_month_active.csv",
                mime="text/csv"
            )
        else:
            st.info("No activities active this month.")
    
    # TAB 3: NEXT MONTH STARTING
    with tab3:
        st.subheader(f"Activities Starting in Next 30 Days ({len(next_month)} items)")
        
        if not next_month.empty:
            # Timeline chart
            if 'current_start' in next_month.columns and 'current_finish' in next_month.columns:
                timeline_df = next_month.head(20).copy()
                
                fig_next = px.timeline(
                    timeline_df,
                    x_start='current_start',
                    x_end='current_finish',
                    y='task_name',
                    title='Top 20 Upcoming Activities',
                    color_discrete_sequence=['#FFA500'],
                    hover_data=['task_id', 'task_code', 'target_drtn_hr_cnt'] if 'task_id' in timeline_df.columns else ['task_code', 'target_drtn_hr_cnt']
                )
                fig_next.update_yaxes(autorange="reversed")
                fig_next.update_layout(height=max(400, len(timeline_df) * 30))
                st.plotly_chart(fig_next, use_container_width=True)
            
            # Detailed table
            st.subheader("Upcoming Activity Details")
            display_cols = ['task_id', 'task_code', 'task_name', 'current_start', 'current_finish', 
                           'target_drtn_hr_cnt', 'total_float_hr_cnt']
            available_cols = [col for col in display_cols if col in next_month.columns]
            
            st.dataframe(next_month[available_cols].head(50), use_container_width=True, height=400)
            
            # Export option
            csv = next_month[available_cols].to_csv(index=False)
            st.download_button(
                label="📥 Download Next Month Starting",
                data=csv,
                file_name="next_month_starting.csv",
                mime="text/csv"
            )
        else:
            st.info("No activities starting in the next 30 days.")
    
    st.divider()
    
    # --- USAGE TIPS ---
    st.info("""
    💡 **Tips:**
    - Use **Last Month** data for progress reports and stakeholder updates
    - Focus on **This Month** activities for daily/weekly coordination
    - Review **Next Month** for resource planning and procurement readiness
    - Export CSV files for integration with other reporting tools
    """)

def render_compare_schedules(parser_current, analyzer_current):
    st.header("Schedule Comparison & Change Detection")
    
    st.markdown("""
    Upload a previous version of your schedule to detect changes, slips, and new activities.
    """)
    
    comparison_file = st.file_uploader(
        "Upload Previous Schedule (.xer)", 
        type="xer", 
        key="comparison_file",
        help="Upload an older version of the schedule to compare against the current version"
    )
    
    if comparison_file:
        try:
            with st.spinner("Analyzing changes..."):
                parser_old, analyzer_old = load_and_parse_xer(comparison_file.getvalue(), comparison_file.name)
                
                # Run diff engine
                diff = DiffEngine(parser_old, parser_current)
                results = diff.run_diff()
                
                # Summary Metrics
                col1, col2, col3 = st.columns(3)
                col1.metric("Activities Added", len(results['added']), delta=f"+{len(results['added'])}")
                col2.metric("Activities Deleted", len(results['deleted']), delta=f"-{len(results['deleted'])}")
                col3.metric("Activities Slipped", len(results['slips'][results['slips']['slip_days'] > 0]))
                
                st.divider()
                
                # Detailed Results
                tab_added, tab_deleted, tab_slips = st.tabs(["➕ Added", "➖ Deleted", "📉 Date Slips"])
                
                with tab_added:
                    if not results['added'].empty:
                        st.subheader(f"New Activities ({len(results['added'])})")
                        st.dataframe(
                            results['added'][['task_name', 'target_start_date', 'target_end_date', 'status_code']],
                            use_container_width=True
                        )
                    else:
                        st.info("✅ No new activities added")
                
                with tab_deleted:
                    if not results['deleted'].empty:
                        st.subheader(f"Removed Activities ({len(results['deleted'])})")
                        st.dataframe(
                            results['deleted'][['task_name', 'target_start_date', 'target_end_date', 'status_code']],
                            use_container_width=True
                        )
                    else:
                        st.info("✅ No activities removed")
                
                with tab_slips:
                    if not results['slips'].empty:
                        st.subheader(f"Date Changes ({len(results['slips'])})")
                        
                        # Visualize slips
                        fig = px.bar(
                            results['slips'].head(20),
                            x='slip_days',
                            y='task_name',
                            orientation='h',
                            title="Top 20 Schedule Slips (Days)",
                            color='slip_days',
                            color_continuous_scale=['green', 'yellow', 'red']
                        )
                        fig.update_layout(height=600, yaxis={'autorange': 'reversed'})
                        st.plotly_chart(fig, use_container_width=True)
                        
                        # Data table
                        def highlight_slips(val):
                            if pd.isna(val):
                                return ''
                            if val > 10:
                                return 'background-color: #ff6666; color: white; font-weight: bold'
                            elif val > 5:
                                return 'background-color: #ffcc66'
                            elif val > 0:
                                return 'background-color: #ffffcc'
                            else:
                                return 'background-color: #ccffcc'
                        
                        styled_slips = results['slips'].style.applymap(highlight_slips, subset=['slip_days'])
                        st.dataframe(styled_slips, use_container_width=True, height=400)
                    else:
                        st.success("✅ No date changes detected - schedule is stable!")
        
        except Exception as e:
            st.error(f"❌ Error comparing schedules: {str(e)}")
            if st.button("Show Error Details"):
                st.exception(e)
    else:
        st.info("👆 Upload a previous schedule version above to begin comparison")

def render_data_tables(analyzer):
    st.header("Detailed Data Views")
    
    view_option = st.selectbox(
        "Select View",
        ["Full Schedule", "Critical Path Only", "Procurement Log", "Milestones Only"]
    )
    
    # Search and filter
    col1, col2 = st.columns([3, 1])
    with col1:
        search_term = st.text_input("🔍 Search activities", placeholder="Enter activity name or code...")
    with col2:
        status_filter = st.multiselect("Filter by Status", 
                                      ["Not Started", "In Progress", "Completed"],
                                      default=["Not Started", "In Progress"])
    
    # Get data based on view
    if view_option == "Full Schedule":
        df = analyzer.df_main
    elif view_option == "Critical Path Only":
        df = analyzer.get_critical_path()
    elif view_option == "Procurement Log":
        df = analyzer.get_procurement_log()
    else:  # Milestones Only
        df = analyzer.get_milestones()
    
    # Apply filters
    if search_term:
        mask = df['task_name'].str.contains(search_term, case=False, na=False) | \
               df['task_code'].astype(str).str.contains(search_term, case=False, na=False)
        df = df[mask]
    
    if status_filter and 'status_readable' in df.columns:
        df = df[df['status_readable'].isin(status_filter)]
    
    # Display
    st.write(f"**Showing {len(df)} activities**")
    
    # Column selector
    available_cols = ['task_code', 'task_name', 'current_start', 'current_finish', 
                     'variance_days', 'status_readable']
    selected_cols = st.multiselect(
        "Select columns to display",
        [col for col in available_cols if col in df.columns],
        default=[col for col in available_cols if col in df.columns][:5]
    )
    
    if selected_cols:
        # Format dates as MM/DD/YYYY
        display_df = df[selected_cols].copy()
        for col in ['current_start', 'current_finish']:
            if col in display_df.columns:
                display_df[col] = pd.to_datetime(display_df[col]).dt.strftime('%m/%d/%Y')
        
        st.dataframe(display_df, use_container_width=True, height=600)
    
    # Export option
    if st.button("📥 Export to CSV"):
        csv = df.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"sixterm_export_{view_option.lower().replace(' ', '_')}.csv",
            mime="text/csv"
        )

def render_sidebar_ai_copilot():
    """Compact AI Copilot in sidebar"""
    st.subheader("🤖 AI Copilot")
    
    # Check if schedule is loaded
    has_parser = hasattr(st.session_state, 'parser') and st.session_state.parser is not None
    has_analyzer = hasattr(st.session_state, 'analyzer') and st.session_state.analyzer is not None
    
    if not has_parser or not has_analyzer:
        st.info("📁 Upload a schedule to enable AI Copilot")
        # Debug info
        if st.checkbox("Show debug", key="debug_copilot"):
            st.write(f"Parser: {has_parser}, Analyzer: {has_analyzer}")
            st.write(f"Session state keys: {list(st.session_state.keys())}")
        return
    
    # Check API key
    api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.warning("⚠️ Configure API key in Settings")
        return
    
    # Initialize copilot
    try:
        copilot = ScheduleCopilot(st.session_state.parser, st.session_state.analyzer)
    except Exception as e:
        st.error(f"❌ {str(e)[:50]}...")
        return
    
    # Current context
    current_view = st.session_state.get('current_view', 'Dashboard')
    st.caption(f"📍 {current_view}")
    
    # Recent chat
    if len(st.session_state.messages) > 0:
        with st.expander("💬 Chat", expanded=False):
            for msg in st.session_state.messages[-2:]:
                icon = "U" if msg["role"] == "user" else "6"
                st.markdown(f"**{icon}** {msg['content'][:80]}...")
    
    # Quick questions
    st.caption("Quick questions:")
    for q in ["Top risks?", "Project status?"]:
        if st.button(q, key=f"q_{q}", use_container_width=True):
            st.session_state.messages.append({"role": "user", "content": q})
            try:
                history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
                response = copilot.query(q, history, current_view=current_view)
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.rerun()
            except Exception as e:
                st.error(f"Error: {str(e)[:50]}...")
    
    # Input
    with st.form(key="sb_chat", clear_on_submit=True):
        prompt = st.text_area("Ask...", key="sb_ai", height=60, placeholder="Ask about schedule...")
        send = st.form_submit_button("Send ➤", use_container_width=True)
    
    if send and prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        try:
            history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
            local_response = None
            t = prompt.strip().lower()
            if re.search(r"\b(what\s+page|what\s+tab|where\s+am\s+i|which\s+page|which\s+tab)\b", t):
                local_response = f"You're currently on: {current_view}."

            if local_response is not None:
                response = local_response
            else:
                with st.spinner("Thinking..."):
                    response = copilot.query(prompt, history, current_view=current_view)
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.rerun()
        except Exception as e:
            st.session_state.messages.append({"role": "assistant", "content": f"❌ {str(e)}"})
            st.rerun()



def render_ai_copilot(parser, analyzer):
    st.header("AI Schedule Copilot 🤖")
    
    # Check if API key is configured
    api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        st.warning("⚠️ AI Copilot requires an OpenAI API key. Configure it in Settings.")
        if st.button("Go to Settings"):
            st.session_state.page = "⚙️ Settings"
            st.rerun()
        return
    
    # Initialize copilot with retry logic
    try:
        copilot = ScheduleCopilot(parser, analyzer)
    except Exception as e:
        st.error(f"❌ Failed to initialize AI Copilot: {str(e)}")
        return
    
    # Suggested questions
    st.subheader("Suggested Questions")
    suggestions = [
        "What are the top 3 schedule risks?",
        "Why is the project delayed?",
        "Which milestones are at risk?",
        "Show me activities with the most float",
        "What's the longest path in the schedule?"
    ]
    
    cols = st.columns(len(suggestions))
    for idx, suggestion in enumerate(suggestions):
        if cols[idx].button(suggestion, key=f"suggest_{idx}", use_container_width=True):
            st.session_state.messages.append({"role": "user", "content": suggestion})
    
    st.divider()
    
    # Chat interface with custom avatars
    for message in st.session_state.messages:
        avatar = "U" if message["role"] == "user" else "6"
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])
    
    # Chat input with form (Enter to submit, Shift+Enter for new line)
    with st.form(key="chat_form", clear_on_submit=True):
        prompt = st.text_area(
            "Ask about your schedule...", 
            key="ai_prompt", 
            height=80, 
            label_visibility="collapsed", 
            placeholder="Ask about your schedule... (Enter to send, Shift+Enter for new line)"
        )
        send_button = st.form_submit_button("Send ➤", use_container_width=True)
    
    if send_button and prompt:
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Get AI response with retry logic
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                # Build chat history for context
                chat_history = [
                    {"role": msg["role"], "content": msg["content"]} 
                    for msg in st.session_state.messages[:-1]
                ]
                
                with st.spinner("Thinking..."):
                    current_view = st.session_state.get('current_view', 'AI Copilot')
                    local_response = None
                    t = prompt.strip().lower()
                    if re.search(r"\b(what\s+page|what\s+tab|where\s+am\s+i|which\s+page|which\s+tab)\b", t):
                        local_response = f"You're currently on: {current_view}."

                    if local_response is not None:
                        response = local_response
                    else:
                        response = copilot.query(prompt, chat_history, current_view=current_view)
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.rerun()
                break
            
            except Exception as e:
                if attempt < max_retries - 1:
                    st.warning(f"Retry {attempt + 1}/{max_retries}...")
                    time.sleep(retry_delay * (attempt + 1))
                else:
                    error_msg = f"❌ AI Error after {max_retries} attempts: {str(e)}"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
                    st.rerun()

def render_settings_page():
    st.title("⚙️ Settings")
    
    st.subheader("AI Configuration")

    ai_mode = st.radio(
        "AI Mode",
        ["cloud", "internal"],
        index=0 if (config.get("ai_mode") or "cloud") == "cloud" else 1,
        help="Cloud: sanitize project name in Copilot prompts. Internal: use real project name.",
        horizontal=True
    )

    project_alias = st.text_input(
        "Project Alias (Cloud Mode)",
        value=config.get("project_alias", "Stelic Project"),
        help="Used as the project name in Copilot prompts when AI Mode is Cloud."
    )
    
    # API Key
    api_key = st.text_input(
        "OpenAI API Key",
        value=config.get("api_key", ""),
        type="password",
        help="Your OpenAI API key for the AI Copilot feature"
    )
    
    # Model selection
    model = st.selectbox(
        "AI Model",
        ["gpt-4-turbo", "gpt-4", "gpt-3.5-turbo", "gpt-4.1-mini"],
        index=0 if config.get("ai_model") == "gpt-4-turbo" else 0
    )
    
    # Base URL (for custom endpoints)
    base_url = st.text_input(
        "API Base URL",
        value=config.get("api_base_url", "https://api.openai.com/v1"),
        help="Change this for OpenRouter, LocalAI, or other compatible APIs"
    )
    
    st.divider()
    
    st.subheader("Analysis Thresholds")
    
    col1, col2 = st.columns(2)
    with col1:
        critical_float = st.number_input(
            "Critical Path Float Threshold (hours)",
            value=config.get("analysis", {}).get("critical_float_threshold", 0),
            min_value=0,
            max_value=480,
            help="Activities with float <= this value are considered critical"
        )
    
    with col2:
        slippage_threshold = st.number_input(
            "Slippage Threshold (days)",
            value=config.get("analysis", {}).get("slippage_threshold_days", 5),
            min_value=1,
            max_value=90,
            help="Activities slipping more than this are flagged as high risk"
        )
    
    st.divider()
    
    # Save button
    if st.button("💾 Save Settings", type="primary"):
        new_config = {
            "ai_mode": ai_mode,
            "project_alias": project_alias,
            "api_key": api_key,
            "ai_model": model,
            "api_base_url": base_url,
            "analysis": {
                "critical_float_threshold": critical_float,
                "slippage_threshold_days": slippage_threshold
            }
        }
        config.save(new_config)
        st.success("✅ Settings saved successfully!")
        time.sleep(1)
        st.rerun()
    
    # Clear cache
    if st.button("🗑️ Clear Cache"):
        st.cache_data.clear()
        st.success("✅ Cache cleared!")

def render_help_page():
    st.title("📖 Help & Documentation")
    
    st.markdown("""
    ## Getting Started
    
    ### 1. Upload Your Schedule
    - Click "Upload Schedule (.xer)" in the sidebar
    - Select a valid Primavera P6 XER export file
    - The file will be automatically parsed and analyzed
    
    ### 2. Explore the Dashboard
    - **Executive Summary**: High-level project health metrics
    - **Stairway Visuals**: Milestone progression tracking
    - **Compare Schedules**: Detect changes between versions
    - **Data Tables**: Detailed activity views with search/filter
    - **AI Copilot**: Ask natural language questions
    
    ### 3. Generate Reports
    - Click "Generate Excel Report" to create a stakeholder-ready dashboard
    - The Excel file includes formatted tables, charts, and conditional formatting
    
    ## Features
    
    ### Schedule Analysis
    - Automatic critical path identification
    - Variance analysis (baseline vs current)
    - Milestone tracking
    - Procurement log extraction
    
    ### Change Detection
    - Compare two schedule versions
    - Identify added/deleted activities
    - Track date slips and improvements
    - Visual slip analysis
    
    ### AI Copilot
    - Natural language schedule queries
    - Context-aware responses
    - Suggested questions for common analyses
    - Chat history for follow-up questions
    
    ## Troubleshooting
    
    **File Upload Errors**
    - Ensure the file is a valid .xer export from P6
    - Check that the file isn't corrupted
    - Try re-exporting from P6 if issues persist
    
    **AI Copilot Not Working**
    - Configure your OpenAI API key in Settings
    - Check your API key has sufficient credits
    - Verify internet connectivity
    
    **Performance Issues**
    - Large schedules (>5000 activities) may take longer to process
    - Use the "Clear Cache" button in Settings if needed
    - Consider filtering data in the Data Tables view
    
    ## Support
    
    For issues, feature requests, or questions:
    - GitHub: https://github.com/bloXbandit/SixTerminal
    - Documentation: [Coming Soon]
    
    ## Version
    **SixTerminal v2.0** - Production Release
    """)

if __name__ == "__main__":
    main()
