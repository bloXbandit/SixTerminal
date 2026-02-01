import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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

# Page Config
st.set_page_config(
    page_title="SixTerminal | P6 Stairway Tracker",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #4CAF50;
    }
    .critical-card {
        border-left: 5px solid #F44336;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px;
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

@st.cache_data(ttl=3600)
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
        st.title("SixTerminal 🏗️")
        st.caption("P6 Stairway Tracker & AI Copilot")
        
        # Navigation
        page = st.radio("Navigate", ["📊 Dashboard", "⚙️ Settings", "📖 Help"], label_visibility="collapsed")
        
        st.divider()
        
        if page == "📊 Dashboard":
            uploaded_file = st.file_uploader("Upload Schedule (.xer)", type="xer", key="main_file")
            
            if uploaded_file:
                st.success("✅ File Loaded")
                
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
        if 'uploaded_file' in locals() and uploaded_file:
            render_dashboard(uploaded_file)
        else:
            render_landing_page()
    elif page == "⚙️ Settings":
        pass  # Already rendered in sidebar
    elif page == "📖 Help":
        pass  # Already rendered in sidebar

def render_landing_page():
    st.title("Welcome to SixTerminal")
    st.markdown("""
    ### The Modern Interface for Primavera P6
    
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
        st.metric("AI Models", "GPT-4+")

def render_dashboard(uploaded_file):
    try:
        # Load with caching
        parser, analyzer = load_and_parse_xer(uploaded_file.getvalue(), uploaded_file.name)
        
        # --- TAB STRUCTURE ---
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "🚀 Executive Summary", 
            "📈 Stairway Visuals", 
            "🔍 Compare Schedules",
            "📋 Data Tables", 
            "🤖 AI Copilot"
        ])
        
        stats = analyzer.get_dashboard_summary()
        
        with tab1:
            render_executive_summary(analyzer, stats)
        
        with tab2:
            render_stairway_visuals(analyzer)
        
        with tab3:
            render_compare_schedules(parser, analyzer)
        
        with tab4:
            render_data_tables(analyzer)
        
        with tab5:
            render_ai_copilot(parser, analyzer)
    
    except Exception as e:
        st.error(f"❌ Error processing XER: {str(e)}")
        st.write("Ensure your .xer file is a valid P6 export.")
        if st.button("Show Debug Info"):
            st.exception(e)

def render_executive_summary(analyzer, stats):
    st.header("Project Health Dashboard")
    
    # KPI Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Activities", stats['total_activities'])
    col2.metric("Critical Activities", stats['critical_activities'], 
                delta=f"{stats['percent_critical']}%", delta_color="inverse")
    col3.metric("Slipping (>5 days)", stats['slipping_activities'], delta="-Risk")
    col4.metric("Data Date", stats['data_date'])
    
    st.divider()
    
    # Critical Path Timeline
    st.subheader("Top 10 Critical Path Drivers")
    crit_df = analyzer.get_critical_path().head(10)
    
    if not crit_df.empty:
        fig = px.timeline(
            crit_df, 
            x_start="current_start", 
            x_end="current_finish", 
            y="task_name",
            color="total_float_hr_cnt",
            title="Critical Path Activities",
            labels={"total_float_hr_cnt": "Total Float (Hrs)"}
        )
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("✅ No critical path activities found - project has positive float!")
    
    # Health Indicators
    st.subheader("Schedule Health Indicators")
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

def render_stairway_visuals(analyzer):
    st.header("Milestone Stairway Tracker")
    
    milestones = analyzer.get_milestones()
    
    if not milestones.empty:
        # Enhanced Stairway Chart
        fig = go.Figure()
        
        # Forecast line (the actual stairway)
        fig.add_trace(go.Scatter(
            x=milestones['current_finish'],
            y=milestones['task_name'],
            mode='markers+lines',
            name='Forecast',
            marker=dict(size=12, color='blue', symbol='circle'),
            line=dict(color='blue', width=2)
        ))
        
        # Baseline markers
        fig.add_trace(go.Scatter(
            x=milestones['target_end_date'],
            y=milestones['task_name'],
            mode='markers',
            name='Baseline',
            marker=dict(size=10, color='gray', symbol='diamond-open')
        ))
        
        # Variance lines
        for idx, row in milestones.iterrows():
            if pd.notnull(row['target_end_date']) and pd.notnull(row['current_finish']):
                fig.add_trace(go.Scatter(
                    x=[row['target_end_date'], row['current_finish']],
                    y=[row['task_name'], row['task_name']],
                    mode='lines',
                    line=dict(color='red' if row['variance_days'] > 0 else 'green', 
                             width=1, dash='dot'),
                    showlegend=False,
                    hoverinfo='skip'
                ))
        
        fig.update_layout(
            title="Milestone Progression (Baseline vs Forecast)",
            xaxis_title="Date",
            yaxis_title="Milestone",
            height=max(400, len(milestones) * 40),
            hovermode='closest',
            yaxis=dict(autorange="reversed")
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
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
        
        styled_df = milestones[['task_code', 'task_name', 'target_end_date', 'current_finish', 'variance_days']].style.applymap(
            highlight_variance, subset=['variance_days']
        )
        
        st.dataframe(styled_df, use_container_width=True, height=400)
    else:
        st.warning("⚠️ No milestones found in schedule. Check your activity types.")

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
                     'variance_days', 'total_float_hr_cnt', 'status_readable']
    selected_cols = st.multiselect(
        "Select columns to display",
        [col for col in available_cols if col in df.columns],
        default=[col for col in available_cols if col in df.columns][:5]
    )
    
    if selected_cols:
        st.dataframe(df[selected_cols], use_container_width=True, height=600)
    
    # Export option
    if st.button("📥 Export to CSV"):
        csv = df.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"sixterm_export_{view_option.lower().replace(' ', '_')}.csv",
            mime="text/csv"
        )

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
    
    # Chat interface
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("Ask about your schedule..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Get AI response with retry logic
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                max_retries = 3
                retry_delay = 1
                
                for attempt in range(max_retries):
                    try:
                        # Build chat history for context
                        chat_history = [
                            {"role": msg["role"], "content": msg["content"]} 
                            for msg in st.session_state.messages[:-1]
                        ]
                        
                        response = copilot.query(prompt, chat_history)
                        st.markdown(response)
                        st.session_state.messages.append({"role": "assistant", "content": response})
                        break
                    
                    except Exception as e:
                        if attempt < max_retries - 1:
                            st.warning(f"Retry {attempt + 1}/{max_retries}...")
                            time.sleep(retry_delay * (attempt + 1))
                        else:
                            error_msg = f"❌ AI Error after {max_retries} attempts: {str(e)}"
                            st.error(error_msg)
                            st.session_state.messages.append({"role": "assistant", "content": error_msg})

def render_settings_page():
    st.title("⚙️ Settings")
    
    st.subheader("AI Configuration")
    
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
