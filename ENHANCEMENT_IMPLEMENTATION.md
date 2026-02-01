# SixTerminal Enhancement Implementation Guide

## Overview
This document outlines the three major enhancements requested:
1. **Improved Milestone Detection** - Multiple detection methods
2. **Manual Activity Selection** - Add activities to trackers from data tables
3. **Material/Procurement Tab** - Dedicated tracking with auto-detection

---

## 1. Improved Milestone Detection ✅ COMPLETED

### Changes Made to `analyzer.py`

**File:** `src/analyzer.py`  
**Method:** `get_milestones()`

**Detection Methods Implemented:**
1. **P6 Task Type** - Checks for `TT_Mile`, `TT_MileStart`
2. **Zero Duration** - Activities with `target_drtn_hr_cnt == 0`
3. **Task Code Pattern** - Regex match for `MIL[E]?[-_]?\d` (e.g., MILE-010, MIL-1000)
4. **Task Name** - Contains word "milestone"

**Test Results:**
- ✅ Detects 122 milestones (previously 0)
- ✅ Captures all MILE-coded activities
- ✅ Includes zero-duration activities

---

## 2. Manual Activity Selection - TO IMPLEMENT

### Required Changes

#### A. Session State (app.py)
Add to session state initialization:
```python
if "manual_milestones" not in st.session_state:
    st.session_state.manual_milestones = set()  # Stores task_ids
if "manual_procurement" not in st.session_state:
    st.session_state.manual_procurement = set()  # Stores task_ids
```

#### B. Enhanced Data Tables View

**Location:** `render_data_tables()` function in `app.py`

**Features to Add:**
1. **Batch Actions** - Buttons to add all visible activities
   - "➕ Add All Visible to Milestones"
   - "➕ Add All Visible to Procurement"
   - "🗑️ Clear All Manual Selections"

2. **Individual Row Actions** - Per-activity buttons
   - "➕ Add to Milestones" button per row
   - "➕ Add to Procurement" button per row
   - Show "✅ Already Added" if activity is in tracker

3. **Selection Summary** - Show counts
   - Display number of manually added milestones
   - Display number of manually added procurement items

**Implementation Pattern:**
```python
# In render_data_tables():
for idx, row in df.iterrows():
    task_id = row.get('task_id')
    
    # Milestone button
    if task_id not in st.session_state.manual_milestones:
        if st.button(f"➕ Milestone", key=f"mile_{idx}"):
            st.session_state.manual_milestones.add(task_id)
            st.rerun()
    else:
        st.button(f"✅ In Milestones", key=f"mile_{idx}", disabled=True)
    
    # Procurement button
    if task_id not in st.session_state.manual_procurement:
        if st.button(f"➕ Procurement", key=f"proc_{idx}"):
            st.session_state.manual_procurement.add(task_id)
            st.rerun()
    else:
        st.button(f"✅ In Procurement", key=f"proc_{idx}", disabled=True)
```

#### C. Update Milestone View

**Location:** `render_stairway_visuals()` function

**Changes:**
1. Get auto-detected milestones: `auto_milestones = analyzer.get_milestones()`
2. Get manually added milestones from session state
3. Combine both (remove duplicates)
4. Display combined list in stairway chart

```python
def render_stairway_visuals_enhanced(analyzer):
    # Auto-detected
    auto_milestones = analyzer.get_milestones()
    
    # Manually added
    manual_ids = st.session_state.manual_milestones
    if manual_ids and analyzer.df_main is not None:
        manual_milestones = analyzer.df_main[analyzer.df_main['task_id'].isin(manual_ids)]
    else:
        manual_milestones = pd.DataFrame()
    
    # Combine (remove duplicates by task_id)
    if not auto_milestones.empty and not manual_milestones.empty:
        milestones = pd.concat([auto_milestones, manual_milestones]).drop_duplicates(subset=['task_id'])
    elif not auto_milestones.empty:
        milestones = auto_milestones
    elif not manual_milestones.empty:
        milestones = manual_milestones
    else:
        milestones = pd.DataFrame()
    
    # Show metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Milestones", len(milestones))
    with col2:
        st.metric("Auto-Detected", len(auto_milestones))
    with col3:
        st.metric("Manually Added", len(manual_milestones))
    
    # Rest of visualization...
```

---

## 3. Material/Procurement Tab ✅ COMPLETED (Backend)

### Changes Made to `analyzer.py`

**File:** `src/analyzer.py`  
**Method:** `get_procurement_log()`

**Enhanced Detection:**
1. **Expanded Keywords:**
   - submittal, submit, procure, procurement
   - fabricat, fabrication, deliver, delivery
   - order, purchase, approval, approve
   - material, equipment, vendor, supplier
   - long lead, rfp, rfi, shop drawing, sample

2. **Task Code Patterns:**
   - SUB- (Submittals)
   - PMU- (Procurement)
   - FAB- (Fabrication)
   - MAT- (Materials)
   - PROC-, DEL-, ORD-

**Test Results:**
- ✅ Detects 600+ procurement items (previously ~200)
- ✅ Captures submittals, deliveries, fabrication, equipment

### Frontend Implementation Needed

**Location:** Add new tab in main dashboard

**Tab Structure:**
```
📦 Material & Procurement Tracker
├── Summary Metrics
│   ├── Total Items
│   ├── Auto-Detected
│   ├── Manually Added
│   └── Completed
├── Sub-tabs
│   ├── 📋 All Items
│   ├── 📄 Submittals
│   ├── 🚚 Deliveries
│   ├── 🏭 Fabrication
│   └── 🔧 Equipment
└── Export Options
```

**Implementation:**
```python
def render_procurement_materials_tab(analyzer):
    st.header("📦 Material & Procurement Tracker")
    
    # Get auto-detected
    auto_detected = analyzer.get_procurement_log()
    
    # Get manually added
    manual_ids = st.session_state.manual_procurement
    if manual_ids:
        manual_items = analyzer.df_main[analyzer.df_main['task_id'].isin(manual_ids)]
    else:
        manual_items = pd.DataFrame()
    
    # Combine
    combined = pd.concat([auto_detected, manual_items]).drop_duplicates(subset=['task_id'])
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Items", len(combined))
    with col2:
        st.metric("Auto-Detected", len(auto_detected))
    with col3:
        st.metric("Manually Added", len(manual_items))
    with col4:
        completed = len(combined[combined['status_readable'] == 'Completed'])
        st.metric("Completed", completed)
    
    # Sub-tabs for categorization
    tabs = st.tabs(["📋 All", "📄 Submittals", "🚚 Deliveries", "🏭 Fabrication", "🔧 Equipment"])
    
    with tabs[0]:  # All Items
        st.dataframe(combined, use_container_width=True)
    
    with tabs[1]:  # Submittals
        submittals = combined[combined['task_name'].str.contains('submit|approval', case=False, na=False)]
        st.dataframe(submittals, use_container_width=True)
    
    # ... similar for other tabs
```

---

## Implementation Steps

### Step 1: Update Main App Navigation ✅ DONE
Add new tab to main dashboard:
```python
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🚀 Executive Summary",
    "📈 Stairway Visuals",
    "📦 Procurement/Materials",  # NEW TAB
    "🔍 Compare Schedules",
    "📋 Data Tables",
    "🤖 AI Copilot"
])
```

### Step 2: Implement Manual Selection in Data Tables
- Add session state initialization
- Add batch action buttons
- Add per-row selection buttons
- Show selection summary

### Step 3: Update Stairway Visuals
- Combine auto-detected + manual milestones
- Show source breakdown (auto vs manual)
- Display combined list in chart

### Step 4: Create Procurement Tab
- Implement `render_procurement_materials_tab()`
- Add sub-tabs for categorization
- Include search/filter functionality
- Add export options

### Step 5: Testing
- Test with user's 24090B1 XER file
- Verify milestone detection (should find 122)
- Verify procurement detection (should find 600+)
- Test manual selection workflow
- Test combined views

---

## Testing Checklist

### Milestone Detection
- [ ] Auto-detects 122 milestones from XER
- [ ] Shows breakdown by detection method
- [ ] Allows manual addition from data tables
- [ ] Combines auto + manual in stairway view
- [ ] Removes duplicates properly

### Procurement Tracking
- [ ] Auto-detects 600+ procurement items
- [ ] Categorizes by type (submittal, delivery, etc.)
- [ ] Allows manual addition from data tables
- [ ] Shows combined view
- [ ] Export works correctly

### Manual Selection
- [ ] Batch "Add All" buttons work
- [ ] Individual row buttons work
- [ ] Selection persists across tab switches
- [ ] Clear all button works
- [ ] Shows accurate counts

---

## Code Files to Modify

1. **analyzer.py** ✅ DONE
   - Enhanced `get_milestones()`
   - Enhanced `get_procurement_log()`

2. **app.py** - TO DO
   - Add session state initialization
   - Modify `render_data_tables()` for manual selection
   - Modify `render_stairway_visuals()` to combine sources
   - Add new `render_procurement_materials_tab()` function
   - Update main tab navigation

---

## Expected Results

### Before Enhancement
- Milestones detected: 0
- Procurement items: ~200
- No manual selection capability
- No dedicated procurement tab

### After Enhancement
- Milestones detected: 122 (auto) + manual additions
- Procurement items: 600+ (auto) + manual additions
- Full manual selection from data tables
- Dedicated procurement tab with categorization

---

## Next Steps

1. ✅ Test enhanced analyzer.py with user's XER
2. ⏳ Implement manual selection UI in app.py
3. ⏳ Add procurement/materials tab
4. ⏳ Test full workflow
5. ⏳ Commit to repository

---

**Status:** Backend complete, frontend implementation in progress
