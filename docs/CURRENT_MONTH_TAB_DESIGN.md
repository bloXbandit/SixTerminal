# Current Month Focus Tab - Design Specification

## Purpose
Provide a snapshot of **exactly where the project is right now** based on the P6 data date. Shows what's happening this month, what was recently completed, and what's coming next.

## Logic & Filters

### Data Date Reference
- Use `project.data_date` or most recent `act_start_date` as reference
- All date calculations relative to this data date

### Time Windows

**Last Month (Actuals)**
- Activities that **completed** in the 30 days before data date
- Status: TK_Complete
- `act_end_date` between (data_date - 30 days) and data_date

**This Month (Current Focus)**
- Activities that **should be active** during current month
- Criteria:
  - Start date <= data_date
  - Finish date >= data_date
  - OR status = TK_Active
  - OR scheduled to start/finish within ±15 days of data_date

**Next Month (Upcoming)**
- Activities **starting soon** (next 30 days)
- Status: TK_NotStart
- `early_start_date` or `target_start_date` between data_date and (data_date + 30 days)

## Metrics to Display

### Summary Cards
1. **Data Date** - Current schedule snapshot date
2. **This Month Activities** - Count of activities in current focus
3. **Planned Completions** - Activities scheduled to finish this month
4. **Actual Completions** - Activities that actually finished this month
5. **Completion Rate** - Actual / Planned percentage

### Progress Indicators
- **On Track**: Activities progressing as planned
- **Behind**: Activities started but not progressing (0% complete after start)
- **Ahead**: Activities completed early

## Visualizations

### 1. Monthly Activity Timeline
- Gantt-style chart showing this month's activities
- Color-coded by status
- Highlight data date with vertical line

### 2. Completion Trend
- Bar chart: Last month actuals vs This month planned vs Next month forecast

### 3. Critical Activities This Month
- List of critical path items active this month
- Priority focus for project team

## Tables

### Last Month Completions
Columns: Activity ID, Code, Name, Actual End Date, Duration, Status
- Shows what was accomplished recently
- Useful for monthly reports

### This Month Active
Columns: Activity ID, Code, Name, Start, Finish, % Complete, Float, Status
- Current work in progress
- Highlight activities behind schedule (started but 0% complete)

### Next Month Starting
Columns: Activity ID, Code, Name, Planned Start, Duration, Predecessors
- Upcoming work to prepare for
- Resource planning and procurement readiness

## Color Coding

- 🟢 **Green**: Completed on time or ahead
- 🔵 **Blue**: Active and progressing
- 🟡 **Yellow**: Starting soon (next 7 days)
- 🟠 **Orange**: Behind schedule (started but not progressing)
- 🔴 **Red**: Critical path items at risk

## Use Cases

### Weekly Team Meetings
- "What are we working on this week?"
- "What did we finish last week/month?"
- "What's coming up next?"

### Monthly Reports
- Export last month's completions for stakeholder reporting
- Show current month progress vs plan
- Forecast next month's activities

### Resource Planning
- See what's starting soon
- Identify critical activities needing attention
- Plan material deliveries and crew assignments

## Implementation Notes

### Date Handling
- Handle missing dates gracefully (use early dates if actual dates missing)
- Account for schedules without data date (use today's date)
- Support both baseline and current dates

### Performance
- Cache month calculations
- Limit to reasonable activity counts (top 50 per section)
- Provide "Show All" option for detailed view

### Filters
- Allow user to adjust time window (7/14/30/60 days)
- Filter by WBS, responsible party, activity type
- Search within current month activities
