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
                data_date = datetime.strptime(metrics['data_date'], '%Y-%m-%d')
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
