# Enhanced AI Copilot Design - Master Scheduler Assistant

## Executive Summary

Transform 6ix Copilot from a basic Q&A bot into a **true master scheduler assistant** that:
- Accurately extracts and analyzes XER data
- Tells compelling project stories based on actual activities
- Follows DCMA 14-point assessment framework
- Understands construction sequencing and logic
- Adapts tone from simplistic to narrative based on context

---

## Core Problems Identified

### 1. **Inaccurate Data Extraction**
- Current: Sends 919 WBS nodes (token waste, confusing)
- Fix: Send only Level 1-2 WBS (major phases)

### 2. **No Schedule Quality Assessment**
- Current: No DCMA 14-point checks
- Fix: Implement all 14 metrics

### 3. **No Sequencing Logic**
- Current: Can't answer "what should come before X?"
- Fix: Analyze predecessors/successors, construction best practices

### 4. **No Storytelling**
- Current: Just lists numbers
- Fix: Narrative mode that explains project journey

### 5. **No Role Awareness**
- Current: Generic responses
- Fix: Understand GC, sub, owner, scheduler perspectives

---

## DCMA 14-Point Assessment Framework

The AI will automatically assess these metrics and report on them:

| # | Metric | Description | Threshold |
|---|--------|-------------|-----------|
| 1 | **Logic** | % activities with predecessors & successors | >90% |
| 2 | **Leads** | % relationships with leads | <5% |
| 3 | **Lags** | % relationships with lags | <5% |
| 4 | **Relationship Types** | % Finish-to-Start relationships | >90% |
| 5 | **Hard Constraints** | % activities with constraints | <5% |
| 6 | **High Float** | % activities with >44 days float | <5% |
| 7 | **Negative Float** | % activities with negative float | 0% |
| 8 | **High Duration** | % activities >44 days duration | <5% |
| 9 | **Invalid Dates** | % activities with missing dates | 0% |
| 10 | **Resources** | % activities with resources assigned | >80% |
| 11 | **Missed Tasks** | % incomplete tasks after data date | 0% |
| 12 | **Critical Path Test** | Longest path analysis | Valid |
| 13 | **Critical Path Length Index** | CP length / contract duration | <1.0 |
| 14 | **Baseline** | Baseline schedule exists | Yes |

---

## Enhanced Context Structure

### **Tier 1: Project Identity**
```json
{
  "project_name": "CISA HQ - BASELINE R2",
  "project_type": "Commercial Office Building",  // AI infers from activities
  "data_date": "December 1, 2024",
  "contract_duration_days": 730,
  "percent_time_elapsed": "65%"
}
```

### **Tier 2: Schedule Health (DCMA 14)**
```json
{
  "dcma_score": "11/14 PASS",
  "critical_issues": [
    "135 activities started but 0% complete (Metric #11 FAIL)",
    "5 hard constraints detected (Metric #5 WARNING)"
  ],
  "logic_quality": "Excellent - 99.97% connected",
  "float_health": "Good - 128 critical (2%)"
}
```

### **Tier 3: Project Story Elements**
```json
{
  "current_phase": "Structural Steel & MEP Rough-In",
  "recent_completions": ["Foundation Complete", "Excavation 100%"],
  "active_now": ["Steel Erection L1-L3", "Plumbing Underground"],
  "upcoming_milestones": ["MILE-030: Steel Topping Out (Jan 15)"],
  "behind_schedule": ["135 activities delayed"],
  "procurement_status": "759 items tracked, 6 critical deliveries pending"
}
```

### **Tier 4: Sequencing Intelligence**
```json
{
  "typical_sequences": {
    "excavation": ["Survey", "Demolition", "Excavation", "Shoring", "Foundation"],
    "vertical": ["Foundation", "Columns", "Beams", "Decking", "MEP Rough"],
    "finishes": ["Drywall", "Paint", "Flooring", "Fixtures", "Punch"]
  },
  "current_logic_issues": [
    "FAB-5720 (Caissons) has no predecessor - should follow EXC-1000"
  ]
}
```

---

## AI Personality & Modes

### **Mode 1: Simplistic (Default for Quick Questions)**
**User:** "How many activities?"  
**AI:** "6,495 activities total. 295 complete, 157 active, 6,043 pending."

### **Mode 2: Narrative (For Status Questions)**
**User:** "What's the project status?"  
**AI:** 
> "We're at the critical juncture of this CISA HQ build. As of December 1st, we've completed 295 activities (4.5%) - primarily site prep and foundation work. The team is now focused on two major fronts: structural steel erection (levels 1-3) and underground MEP rough-in. 
>
> Here's the concern: 135 activities show as 'started' but remain at 0% complete. This suggests either a data entry lag or actual work stoppages that need immediate attention. The critical path has 128 activities with zero float - meaning any delay here directly impacts our completion date.
>
> Bottom line: We're in the thick of it. Steel and MEP are the heartbeat right now, but we need to address those stalled activities before they cascade into bigger problems."

### **Mode 3: DCMA Assessment (For Schedule Quality Questions)**
**User:** "How's the schedule quality?"  
**AI:**
> "Running a DCMA 14-point check on this schedule:
>
> **PASSING (11/14):**
> ✅ Logic: 99.97% connected (only 1 open start, 1 open end)  
> ✅ Relationships: 82.7% FS, 8.9% SS, 8.4% FF - good mix  
> ✅ Constraints: Only 5 (0.08%) - excellent  
> ✅ Float: 128 critical (2%) - manageable  
>
> **FAILING (3/14):**
> ❌ Missed Tasks: 135 activities started but 0% complete  
> ⚠️ High Duration: Need to check for activities >44 days  
> ⚠️ Resources: No resource data in XER  
>
> **Recommendation:** This is a well-structured schedule with strong logic. Priority #1 is updating those 135 stalled activities. Otherwise, you're in good shape for project controls."

### **Mode 4: Sequencing Advisor (For Logic Questions)**
**User:** "What should come before steel erection?"  
**AI:**
> "For steel erection, the typical sequence is:
>
> **Prerequisites (Must Complete First):**
> 1. Foundation/Footings - 100% complete and cured (28 days min)
> 2. Anchor Bolts - Set and inspected
> 3. Survey Control Points - Established
> 4. Crane Mobilization - On-site and certified
> 5. Steel Fabrication - Delivered to site (long-lead item!)
>
> **In Your Schedule:**
> Looking at your activities, I see FAB-5720 (Stability Caissons) and DEL-5720 (Deliver Caissons) should precede any vertical steel. Make sure EXC-1000 (Excavation) → FAB-5720 → DEL-5720 → Steel Erection is properly linked.
>
> **Pro Tip:** Steel erection is on the critical path 99% of the time. Any delay here ripples through the entire project. Coordinate with your fabricator NOW on delivery dates."

---

## Construction Role Perspectives

The AI will detect project type and adopt appropriate perspectives:

### **General Contractor Perspective**
- Focus: Schedule compression, subcontractor coordination, milestone dates
- Language: "We need to pull in the MEP subs for a coordination meeting..."

### **Subcontractor Perspective**  
- Focus: Predecessor completion, material deliveries, manpower planning
- Language: "Before we can start drywall, we need MEP rough-in signed off..."

### **Owner/Client Perspective**
- Focus: Substantial completion, budget impact, milestone achievements
- Language: "You're tracking toward a Q2 2025 occupancy, but those 135 stalled activities are a red flag..."

### **Scheduler Perspective** (Default)
- Focus: Logic, float, critical path, DCMA compliance
- Language: "Your critical path has 128 activities. Let's talk about float management..."

---

## Implementation Plan

### **Phase 1: Enhanced Context Extraction** (parser.py)
- Limit WBS to Level 1-2 only (5-10 nodes max)
- Add DCMA 14-point calculations
- Extract sequencing patterns from relationships
- Infer project type from activity names

### **Phase 2: Intelligent Prompting** (copilot.py)
- Dynamic system prompt based on query type
- Mode detection (simplistic vs narrative)
- Role-based language adaptation
- DCMA assessment integration

### **Phase 3: Function Calling** (Optional - Advanced)
- `get_activities_by_wbs(wbs_code)` - Drill into specific phases
- `get_predecessors(activity_id)` - Show what must complete first
- `get_successors(activity_id)` - Show what's waiting
- `check_sequencing(activity_a, activity_b)` - Validate logic

---

## Success Metrics

**Before:**
- AI says "6,495 activities" when asked "how many" ❌ (Wrong count)
- No storytelling, just lists numbers
- Can't answer sequencing questions
- No schedule quality assessment

**After:**
- AI accurately reports 6,495 activities ✅
- Tells project story: "We're in steel erection phase, 4.5% complete..."
- Answers: "Steel should follow foundation, anchor bolts, and crane setup"
- Reports: "DCMA Score: 11/14 - Address 135 stalled activities"

---

## Token Optimization

**Current:** ~3,000 tokens per query (919 WBS nodes!)  
**Target:** ~800 tokens per query (smart summarization)

**Savings:** 73% reduction in API costs while improving quality!

---

## Next Steps

1. ✅ Design complete (this document)
2. ⏭️ Implement enhanced `get_llm_context()` in parser.py
3. ⏭️ Rewrite copilot.py system prompt with modes
4. ⏭️ Add DCMA calculations to analyzer.py
5. ⏭️ Test with user's XER file
6. ⏭️ Deploy and iterate based on feedback

---

**End of Design Document**
