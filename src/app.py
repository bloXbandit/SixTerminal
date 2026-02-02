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
        background-color: #1e293b;
        padding: 8px;
        border-radius: 12px;
    }
    
    .stTabs [data-baseweb="tab"] {
        padding: 12px 24px;
        font-weight: 600;
        border-radius: 8px;
        transition: all 0.3s ease;
        color: #cbd5e1;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background-color: #334155;
    }
    
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background-color: #475569;
        color: #f1f5f9;
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
        st.markdown("<h1 style='margin-top: 20px; margin-bottom: 5px;'>SixTerminal</h1>", unsafe_allow_html=True)
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
        
        # --- TAB STRUCTURE (AI Copilot moved to sidebar) ---
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "🚀 Executive Summary", 
            "📈 Stairway Visuals",
            "📦 Material & Procurement",
            "📅 Current Month Focus",
            "🔍 Compare Schedules",
            "📋 Data Tables"
        ])
        
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
        
        with tab1:
            render_executive_summary(analyzer, stats)
        
        with tab2:
            render_stairway_visuals(analyzer)
        
        with tab3:
            render_procurement_tracker(analyzer)
        
        with tab4:
            render_current_month_focus(analyzer)
        
        with tab5:
            render_compare_schedules(parser, analyzer)
        
        with tab6:
            render_data_tables(analyzer)
        
    
    except Exception as e:
        st.error(f"❌ Error processing XER: {str(e)}")
        st.write("Ensure your .xer file is a valid P6 export.")
        if st.button("Show Debug Info"):
            st.exception(e)

def render_executive_summary(analyzer, stats):
    # Header with icon
    st.markdown("## 📊 Project Health Dashboard")
    st.divider()
    
    # Get project duration metrics
    duration_info = analyzer.get_project_duration()
    
    # KPI Metrics
    st.markdown("### Key Performance Indicators")
    
    # First row - Core metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Activities", stats['total_activities'])
    col2.metric("Critical Activities", stats['critical_activities'], 
                delta=f"{stats['percent_critical']}%", delta_color="inverse")
    col3.metric("Slipping (>5 days)", stats['slipping_activities'], delta="-Risk")
    col4.metric("Data Date", stats['data_date'])
    
    # Second row - Duration metrics
    col5, col6, col7, col8 = st.columns(4)
    col5.metric("📅 Project Duration", f"{duration_info['duration_days']:,} days")
    col6.metric("✅ Duration % Complete", f"{duration_info['percent_complete']}%", 
                delta=f"{duration_info['percent_complete']}%")
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
        fig.update_layout(height=500)
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
                        st.write(f"- {cstr}: {count}")
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
        # Add task_code to milestone display names
        if 'task_code' in milestones.columns:
            milestones['display_name'] = milestones['task_name'] + ' (' + milestones['task_code'].astype(str) + ')'
        else:
            milestones['display_name'] = milestones['task_name']
        
        # Enhanced Stairway Chart
        fig = go.Figure()
        
        # Forecast line (the actual stairway)
        fig.add_trace(go.Scatter(
            x=milestones['current_finish'],
            y=milestones['display_name'],
            mode='markers+lines',
            name='Forecast',
            marker=dict(size=12, color='blue', symbol='circle'),
            line=dict(color='blue', width=2)
        ))
        
        # Baseline markers
        fig.add_trace(go.Scatter(
            x=milestones['target_end_date'],
            y=milestones['display_name'],
            mode='markers',
            name='Baseline',
            marker=dict(size=10, color='gray', symbol='diamond-open')
        ))
        
        # Variance lines
        for idx, row in milestones.iterrows():
            if pd.notnull(row['target_end_date']) and pd.notnull(row['current_finish']):
                fig.add_trace(go.Scatter(
                    x=[row['target_end_date'], row['current_finish']],
                    y=[row['display_name'], row['display_name']],
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
        
        st.dataframe(styled_df, use_container_width=True, height=400)
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
                    response = copilot.query(prompt, chat_history)
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
