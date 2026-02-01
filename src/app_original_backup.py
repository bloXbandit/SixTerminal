import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from parser import P6Parser
from analyzer import ScheduleAnalyzer
from dashboard import DashboardGenerator
from copilot import ScheduleCopilot
import os
import tempfile

# Page Config
st.set_page_config(
    page_title="SixTerminal | P6 Stairway Tracker",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for "Pro" look
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
</style>
""", unsafe_allow_html=True)

# Session State for Chat
if "messages" not in st.session_state:
    st.session_state.messages = []

def main():
    # --- SIDEBAR ---
    with st.sidebar:
        st.title("SixTerminal 🏗️")
        st.caption("P6 Stairway Tracker & AI Copilot")
        
        uploaded_file = st.file_uploader("Upload Schedule (.xer)", type="xer")
        
        st.divider()
        
        if uploaded_file:
            st.success("File Loaded Successfully")
            
            # Options
            st.subheader("Settings")
            cp_threshold = st.slider("Critical Path Float (Hrs)", 0, 480, 0)
            
            # Action Buttons
            if st.button("Generate Excel Report 📊"):
                with st.spinner("Generating Dashboard..."):
                    # Process
                    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".xer")
                    tfile.write(uploaded_file.getvalue())
                    tfile.close()
                    
                    parser = P6Parser(tfile.name)
                    analyzer = ScheduleAnalyzer(parser)
                    
                    output_path = f"dashboard_{uploaded_file.name}.xlsx"
                    gen = DashboardGenerator(analyzer, output_path)
                    gen.generate()
                    
                    # Download Link
                    with open(output_path, "rb") as f:
                        st.download_button(
                            label="Download Excel File",
                            data=f,
                            file_name=output_path,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    st.success("Dashboard Generated!")

    # --- MAIN CONTENT ---
    if not uploaded_file:
        render_landing_page()
    else:
        render_dashboard(uploaded_file)

def render_landing_page():
    st.title("Welcome to SixTerminal")
    st.markdown("""
    ### The Modern Interface for Primavera P6
    
    Drag and drop your **.xer** file in the sidebar to begin.
    
    **Features:**
    - 📊 **Stairway Visualization:** Track milestone progression.
    - 🧠 **AI Copilot:** Ask questions like *"Why is the foundation delayed?"*
    - ⚡ **Auto-Analysis:** Instant Critical Path & Variance detection.
    - 📑 **Excel Exports:** Stakeholder-ready reports.
    """)

def render_dashboard(uploaded_file):
    # Save temp file for parser (Parser expects path, Streamlit gives bytes)
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".xer")
    tfile.write(uploaded_file.getvalue())
    tfile.close()

    # --- LOAD ENGINE ---
    try:
        parser = P6Parser(tfile.name)
        analyzer = ScheduleAnalyzer(parser)
        
        # --- TAB STRUCTURE ---
        tab1, tab2, tab3, tab4 = st.tabs(["🚀 Executive Summary", "📈 Stairway Visuals", "📋 Data Tables", "🤖 AI Copilot"])
        
        stats = analyzer.get_dashboard_summary()
        
        with tab1:
            st.header("Project Health")
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Activities", stats['total_activities'])
            col2.metric("Critical Activities", stats['critical_activities'], delta_color="inverse")
            col3.metric("Slipping (>5 days)", stats['slipping_activities'], delta="-Risk")
            col4.metric("% Critical", f"{stats['percent_critical']}%")
            
            st.divider()
            
            # Simple Gantt/Timeline Preview (Top Critical Items)
            st.subheader("Top Critical Path Items")
            crit_df = analyzer.get_critical_path().head(10)
            if not crit_df.empty:
                # Use Plotly Timeline
                fig = px.timeline(
                    crit_df, 
                    x_start="current_start", 
                    x_end="current_finish", 
                    y="task_name",
                    color="total_float_hr_cnt",
                    title="Critical Path Driver (Next 10 Items)"
                )
                fig.update_yaxes(autorange="reversed") # Top to bottom
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No critical path activities found.")

        with tab2:
            st.header("Milestone Stairway Tracker")
            milestones = analyzer.get_milestones()
            
            if not milestones.empty:
                # Create the Stairway Chart
                # X = Date, Y = Milestone Name (sorted by date)
                fig = px.scatter(
                    milestones,
                    x="current_finish",
                    y="task_name",
                    color="variance_days",
                    color_continuous_scale=["green", "yellow", "red"],
                    size=[10]*len(milestones), # Fixed dot size
                    title="Milestone Progression (The Stairway)"
                )
                
                # Add Baseline markers (Ghost dots)
                fig.add_trace(go.Scatter(
                    x=milestones['target_end_date'],
                    y=milestones['task_name'],
                    mode='markers',
                    marker=dict(symbol='circle-open', color='gray', size=8),
                    name='Baseline Date'
                ))
                
                fig.update_yaxes(autorange="reversed") # Earliest at top
                st.plotly_chart(fig, use_container_width=True)
                
                # Variance Table
                st.dataframe(
                    milestones[['task_code', 'task_name', 'target_end_date', 'current_finish', 'variance_days']],
                    use_container_width=True
                )
            else:
                st.warning("No milestones found in schedule.")

        with tab3:
            st.header("Deep Dive Data")
            option = st.selectbox("Select View", ["Full Schedule", "Procurement Log", "Logic Issues"])
            
            if option == "Full Schedule":
                st.dataframe(analyzer.df_main)
            elif option == "Procurement Log":
                st.dataframe(analyzer.get_procurement_log())
            else:
                st.write("Logic checks coming in Phase 2.")

        with tab4:
            st.header("AI Schedule Copilot")
            
            # Display Chat History
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

            # Input
            if prompt := st.chat_input("Ask about the schedule..."):
                # User Message
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)

                # AI Response (Stub for now)
                with st.chat_message("assistant"):
                    # Here we connect Copilot class later
                    response = f"I see you asked: '{prompt}'. (AI logic connecting soon...)"
                    st.markdown(response)
                    st.session_state.messages.append({"role": "assistant", "content": response})

    except Exception as e:
        st.error(f"Error processing XER: {e}")
        st.write("Ensure your .xer file is valid P6 export.")

if __name__ == "__main__":
    main()
