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
        'task_id', 'task_code', 'task_name', 'status_code',
        'current_start', 'current_finish', 'complete_pct'
    ]
    available_cols = [col for col in display_cols if col in filtered_df.columns]
    
    # Color code by status
    def highlight_status(row):
        if 'status_code' not in row:
            return [''] * len(row)
        
        status = row['status_code']
        if status == 'TK_Complete':
            color = 'background-color: #d4edda'  # Green
        elif status == 'TK_Active':
            color = 'background-color: #d1ecf1'  # Blue
        elif status == 'TK_NotStart':
            color = 'background-color: #fff3cd'  # Yellow
        else:
            color = ''
        
        return [color] * len(row)
    
    styled_df = filtered_df[available_cols].style.apply(highlight_status, axis=1)
    
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
