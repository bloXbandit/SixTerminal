# Live P6 Integration & Change Tracking

**Purpose:** Enable automated schedule synchronization and change detection between Primavera P6 and SixTerminal dashboards  
**Date:** January 30, 2026  
**Status:** Design & Brainstorming

---

## Executive Summary

The ability to track changes in live P6 schedules is critical for maintaining up-to-date dashboards without manual intervention. This document explores multiple integration approaches, from simple file-based monitoring to direct P6 database connections, with detailed analysis of implementation complexity, security considerations, and real-world feasibility.

**Key Question:** How do we detect when an activity name, start date, finish date, or any other schedule attribute changes in P6, and automatically update the dashboard?

---

## Integration Approaches (Ranked by Complexity)

### Approach 1: Manual XER Upload (Baseline - Already Planned)

**How It Works:**
- User exports XER from P6 manually
- Runs SixTerminal with new XER file
- Dashboard regenerates with updated data

**Change Detection:**
- Compare current XER against previous XER (stored locally)
- Generate change log showing differences
- Highlight changed activities in dashboard

**Pros:**
✅ Simple, no P6 integration required  
✅ Works with any P6 version  
✅ No security concerns (air-gapped environments)  
✅ User has full control over when updates occur  

**Cons:**
❌ Manual process, not automated  
❌ Requires user to remember to export  
❌ Delays between P6 updates and dashboard updates  

**Best For:** Small projects, infrequent updates, high-security environments

---

### Approach 2: Automated XER Export via P6 Scheduled Jobs

**How It Works:**
- Configure P6 to auto-export XER files on schedule (daily/weekly)
- XER files saved to network share or cloud storage
- SixTerminal monitors folder for new XER files
- Automatically processes new files and updates dashboard

**Implementation:**

```
┌─────────────────────────────────────────────────────────────┐
│                    PRIMAVERA P6                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Scheduled Job (P6 Job Service)                      │   │
│  │  - Runs daily at 6 AM                                │   │
│  │  - Exports XER to: \\network\p6_exports\project.xer  │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              NETWORK SHARE / CLOUD STORAGE                  │
│  \\network\p6_exports\                                      │
│  ├─ project_2026-01-30.xer                                  │
│  ├─ project_2026-01-29.xer                                  │
│  └─ project_2026-01-28.xer                                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              SIXTERMINAL FILE WATCHER                       │
│  - Monitors folder for new XER files                        │
│  - Detects changes via file timestamp                       │
│  - Triggers dashboard regeneration                          │
│  - Sends notification (email/Slack) when complete           │
└─────────────────────────────────────────────────────────────┘
```

**Change Detection:**
- Compare new XER against previous version
- Generate detailed change log:
  - Activities added/deleted
  - Date changes (start/finish)
  - Name/description changes
  - Logic changes (predecessors/successors)
  - Resource assignments
  - Activity code changes

**Setup Requirements:**
1. **P6 Job Service** configured with export job
2. **Network share** accessible by both P6 and SixTerminal
3. **File watcher script** running as service/daemon
4. **Notification system** (optional)

**Pros:**
✅ Automated, no manual exports  
✅ Works with P6 Professional and EPPM  
✅ Maintains historical XER versions  
✅ Simple to set up (if Job Service available)  
✅ No direct database access required  

**Cons:**
❌ Requires P6 Job Service (EPPM feature, not in P6 Pro standalone)  
❌ Schedule-based, not real-time  
❌ Network share dependency  
❌ File permissions and access issues  

**Best For:** Medium-sized projects, daily/weekly updates, organizations with P6 EPPM

---

### Approach 3: P6 API Integration (P6 EPPM Web Services)

**How It Works:**
- Connect to P6 EPPM via REST API or SOAP Web Services
- Query project data programmatically
- Detect changes by comparing API responses
- Update dashboard incrementally (only changed data)

**Implementation:**

```
┌─────────────────────────────────────────────────────────────┐
│              PRIMAVERA P6 EPPM SERVER                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  P6 Web Services API                                 │   │
│  │  - REST API (P6 v19+)                                │   │
│  │  - SOAP API (older versions)                         │   │
│  │  - Authentication: OAuth 2.0 / Basic Auth            │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTPS
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              SIXTERMINAL API CLIENT                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  P6 API Connector                                    │   │
│  │  - Authenticate with P6                              │   │
│  │  - Query: Projects, Activities, Relationships        │   │
│  │  - Poll for changes every X minutes                  │   │
│  │  - Cache data locally for comparison                 │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Change Detection Engine                             │   │
│  │  - Compare current data vs cached data               │   │
│  │  - Identify deltas (added/modified/deleted)          │   │
│  │  - Generate change events                            │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Dashboard Update Service                            │   │
│  │  - Incremental updates (not full regeneration)       │   │
│  │  - Real-time notifications                           │   │
│  │  - Change log tracking                               │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**API Capabilities:**

**P6 REST API Endpoints:**
```
GET /api/project/{projectId}
GET /api/activity?projectId={projectId}
GET /api/activity/{activityId}
GET /api/relationship?projectId={projectId}
GET /api/activityCode?projectId={projectId}
GET /api/wbs?projectId={projectId}
GET /api/resource?projectId={projectId}
```

**Change Detection Strategy:**
1. **Polling Approach:**
   - Query P6 API every 15-30 minutes
   - Compare response against cached data
   - Detect changes via field-level comparison
   - Store change events in database

2. **LastUpdateDate Filtering:**
   - P6 tracks `LastUpdateDate` for activities
   - Query only activities modified since last check
   - Efficient for large schedules

**Example Python Implementation:**

```python
import requests
from datetime import datetime, timedelta

class P6APIConnector:
    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.last_check = None
    
    def get_changed_activities(self, project_id):
        """Get activities modified since last check"""
        if self.last_check:
            # Filter by LastUpdateDate
            filter_param = f"LastUpdateDate > '{self.last_check.isoformat()}'"
        else:
            # First run, get all activities
            filter_param = None
        
        url = f"{self.base_url}/api/activity"
        params = {
            "projectId": project_id,
            "filter": filter_param
        }
        
        response = self.session.get(url, params=params)
        response.raise_for_status()
        
        activities = response.json()
        self.last_check = datetime.now()
        
        return activities
    
    def detect_changes(self, current_activities, cached_activities):
        """Compare current vs cached to detect specific changes"""
        changes = {
            "added": [],
            "modified": [],
            "deleted": []
        }
        
        current_ids = {a['Id']: a for a in current_activities}
        cached_ids = {a['Id']: a for a in cached_activities}
        
        # Detect added activities
        for act_id in current_ids:
            if act_id not in cached_ids:
                changes["added"].append(current_ids[act_id])
        
        # Detect deleted activities
        for act_id in cached_ids:
            if act_id not in current_ids:
                changes["deleted"].append(cached_ids[act_id])
        
        # Detect modified activities
        for act_id in current_ids:
            if act_id in cached_ids:
                current = current_ids[act_id]
                cached = cached_ids[act_id]
                
                # Compare specific fields
                field_changes = {}
                if current['Name'] != cached['Name']:
                    field_changes['Name'] = {
                        'old': cached['Name'],
                        'new': current['Name']
                    }
                if current['StartDate'] != cached['StartDate']:
                    field_changes['StartDate'] = {
                        'old': cached['StartDate'],
                        'new': current['StartDate']
                    }
                if current['FinishDate'] != cached['FinishDate']:
                    field_changes['FinishDate'] = {
                        'old': cached['FinishDate'],
                        'new': current['FinishDate']
                    }
                
                if field_changes:
                    changes["modified"].append({
                        'activity': current,
                        'changes': field_changes
                    })
        
        return changes
```

**Pros:**
✅ Near real-time updates (15-30 min polling)  
✅ Programmatic access to all P6 data  
✅ Incremental updates (efficient)  
✅ Can trigger webhooks/notifications on changes  
✅ No file management overhead  
✅ Supports multi-project tracking  

**Cons:**
❌ Requires P6 EPPM (not available in P6 Professional standalone)  
❌ API access must be enabled by P6 admin  
❌ Authentication and security configuration  
❌ API rate limits and performance considerations  
❌ Network connectivity required  
❌ More complex implementation  

**Best For:** Large organizations with P6 EPPM, real-time requirements, multiple projects

---

### Approach 4: Direct P6 Database Connection (Advanced)

**How It Works:**
- Connect directly to P6 database (Oracle, SQL Server, PostgreSQL)
- Query tables for schedule data
- Use database triggers or change data capture (CDC) for real-time detection
- Update dashboard immediately when changes occur

**Implementation:**

```
┌─────────────────────────────────────────────────────────────┐
│              P6 DATABASE (Oracle/SQL Server)                │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Core Tables:                                        │   │
│  │  - TASK (activities)                                 │   │
│  │  - TASKPRED (relationships)                          │   │
│  │  - PROJECT                                           │   │
│  │  - PROJWBS                                           │   │
│  │  - TASKRSRC (resource assignments)                   │   │
│  │  - ACTVCODE (activity codes)                         │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Change Tracking:                                    │   │
│  │  - Database triggers on TASK table                   │   │
│  │  - Writes changes to CHANGE_LOG table                │   │
│  │  - Timestamp + user + field + old/new values         │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │ JDBC/ODBC
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              SIXTERMINAL DATABASE CONNECTOR                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Database Client (SQLAlchemy / cx_Oracle)            │   │
│  │  - Read-only connection (security)                   │   │
│  │  - Query TASK, TASKPRED, PROJECT tables              │   │
│  │  - Poll CHANGE_LOG for new entries                   │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Real-Time Change Listener                           │   │
│  │  - Monitors CHANGE_LOG table                         │   │
│  │  - Triggers dashboard updates on changes             │   │
│  │  - Sends notifications (Slack/email)                 │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**Database Schema (Simplified):**

```sql
-- Core P6 tables (read-only access)
TASK
├─ task_id (PK)
├─ task_code (Activity ID)
├─ task_name
├─ target_start_date
├─ target_end_date
├─ act_start_date
├─ act_end_date
├─ remain_drtn_hr_cnt
├─ total_float_hr_cnt
├─ status_code (TK_NotStart, TK_Active, TK_Complete)
└─ last_update_date

-- Custom change tracking table (created by SixTerminal)
CHANGE_LOG
├─ change_id (PK)
├─ task_id (FK)
├─ field_name
├─ old_value
├─ new_value
├─ change_timestamp
├─ change_user
└─ processed (boolean)
```

**Database Trigger Example (Oracle):**

```sql
CREATE OR REPLACE TRIGGER task_change_tracker
AFTER UPDATE ON TASK
FOR EACH ROW
BEGIN
    -- Track activity name changes
    IF :OLD.task_name != :NEW.task_name THEN
        INSERT INTO CHANGE_LOG (task_id, field_name, old_value, new_value, change_timestamp, change_user)
        VALUES (:NEW.task_id, 'task_name', :OLD.task_name, :NEW.task_name, SYSDATE, USER);
    END IF;
    
    -- Track start date changes
    IF :OLD.target_start_date != :NEW.target_start_date THEN
        INSERT INTO CHANGE_LOG (task_id, field_name, old_value, new_value, change_timestamp, change_user)
        VALUES (:NEW.task_id, 'target_start_date', 
                TO_CHAR(:OLD.target_start_date, 'YYYY-MM-DD'),
                TO_CHAR(:NEW.target_start_date, 'YYYY-MM-DD'),
                SYSDATE, USER);
    END IF;
    
    -- Track finish date changes
    IF :OLD.target_end_date != :NEW.target_end_date THEN
        INSERT INTO CHANGE_LOG (task_id, field_name, old_value, new_value, change_timestamp, change_user)
        VALUES (:NEW.task_id, 'target_end_date',
                TO_CHAR(:OLD.target_end_date, 'YYYY-MM-DD'),
                TO_CHAR(:NEW.target_end_date, 'YYYY-MM-DD'),
                SYSDATE, USER);
    END IF;
END;
```

**Python Implementation:**

```python
import cx_Oracle
from datetime import datetime
import time

class P6DatabaseConnector:
    def __init__(self, dsn, username, password):
        self.connection = cx_Oracle.connect(username, password, dsn)
        self.cursor = self.connection.cursor()
    
    def get_all_activities(self, project_id):
        """Query all activities for a project"""
        query = """
        SELECT 
            t.task_id,
            t.task_code,
            t.task_name,
            t.target_start_date,
            t.target_end_date,
            t.act_start_date,
            t.act_end_date,
            t.remain_drtn_hr_cnt,
            t.total_float_hr_cnt,
            t.status_code,
            t.last_update_date
        FROM TASK t
        WHERE t.proj_id = :project_id
        ORDER BY t.task_code
        """
        
        self.cursor.execute(query, project_id=project_id)
        columns = [col[0] for col in self.cursor.description]
        
        activities = []
        for row in self.cursor:
            activity = dict(zip(columns, row))
            activities.append(activity)
        
        return activities
    
    def get_unprocessed_changes(self):
        """Get changes from CHANGE_LOG that haven't been processed"""
        query = """
        SELECT 
            cl.change_id,
            cl.task_id,
            t.task_code,
            t.task_name,
            cl.field_name,
            cl.old_value,
            cl.new_value,
            cl.change_timestamp,
            cl.change_user
        FROM CHANGE_LOG cl
        JOIN TASK t ON cl.task_id = t.task_id
        WHERE cl.processed = 0
        ORDER BY cl.change_timestamp
        """
        
        self.cursor.execute(query)
        columns = [col[0] for col in self.cursor.description]
        
        changes = []
        for row in self.cursor:
            change = dict(zip(columns, row))
            changes.append(change)
        
        return changes
    
    def mark_changes_processed(self, change_ids):
        """Mark changes as processed"""
        query = "UPDATE CHANGE_LOG SET processed = 1 WHERE change_id = :change_id"
        
        for change_id in change_ids:
            self.cursor.execute(query, change_id=change_id)
        
        self.connection.commit()
    
    def listen_for_changes(self, callback, poll_interval=60):
        """Continuously monitor for changes"""
        print(f"Listening for P6 changes (polling every {poll_interval}s)...")
        
        while True:
            changes = self.get_unprocessed_changes()
            
            if changes:
                print(f"Detected {len(changes)} changes")
                callback(changes)  # Trigger dashboard update
                
                # Mark as processed
                change_ids = [c['change_id'] for c in changes]
                self.mark_changes_processed(change_ids)
            
            time.sleep(poll_interval)
```

**Pros:**
✅ Real-time change detection (via triggers)  
✅ Most comprehensive data access  
✅ Works with P6 Professional and EPPM  
✅ Can track who made changes and when  
✅ Highest performance (direct database access)  
✅ No API rate limits  

**Cons:**
❌ Requires DBA access to P6 database  
❌ Security risk (direct database access)  
❌ Requires database trigger creation (may not be allowed)  
❌ Oracle/SQL Server expertise required  
❌ Can violate P6 support agreements (unsupported)  
❌ Schema changes in P6 updates may break integration  
❌ Most complex implementation  

**Best For:** Organizations with full database access, real-time requirements, custom enterprise integrations

**⚠️ WARNING:** Direct database access is typically **not supported** by Oracle/Primavera. Use with caution and ensure you have proper authorization.

---

### Approach 5: P6 Integration API (P6 EPPM Integration API)

**How It Works:**
- Use P6's official Integration API (formerly P6 Integration API / P6 SDK)
- More robust than Web Services, designed for system integrations
- Supports batch operations and complex queries
- Can subscribe to change events (if configured)

**Implementation:**

```
┌─────────────────────────────────────────────────────────────┐
│              P6 EPPM INTEGRATION API                        │
│  - Java-based API                                           │
│  - Supports event subscriptions                             │
│  - Batch data operations                                    │
│  - Transaction support                                      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              JAVA MIDDLEWARE SERVICE                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  P6 Integration API Client (Java)                    │   │
│  │  - Connects to P6 EPPM                               │   │
│  │  - Subscribes to change events                       │   │
│  │  - Exposes REST API for SixTerminal                  │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │ REST API
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              SIXTERMINAL (Python)                           │
│  - Calls Java middleware REST API                           │
│  - Receives change notifications via webhook                │
│  - Updates dashboard                                        │
└─────────────────────────────────────────────────────────────┘
```

**Pros:**
✅ Official Oracle-supported integration method  
✅ Event-driven (push notifications, not polling)  
✅ Comprehensive API coverage  
✅ Transaction support for data integrity  
✅ Best performance for bulk operations  

**Cons:**
❌ Requires Java development (not Python)  
❌ Complex setup and configuration  
❌ Requires P6 EPPM (not P6 Professional)  
❌ Licensing costs may apply  
❌ Steep learning curve  

**Best For:** Enterprise integrations, organizations with Java expertise, mission-critical systems

---

### Approach 6: Hybrid - File Monitor + Change Detection

**How It Works:**
- Combine automated XER export with intelligent change detection
- Monitor folder for new XER files (like Approach 2)
- Advanced diff engine compares XER files
- Generate detailed change reports
- Optional: Push notifications for critical changes

**Implementation:**

```
┌─────────────────────────────────────────────────────────────┐
│              AUTOMATED XER EXPORT                           │
│  - P6 scheduled job OR manual export                        │
│  - Saves to monitored folder                                │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              SIXTERMINAL FILE WATCHER                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  File Monitor Service                                │   │
│  │  - Watches folder for new .xer files                 │   │
│  │  - Triggers processing on new file                   │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  XER Diff Engine                                     │   │
│  │  - Parses current and previous XER                   │   │
│  │  - Field-by-field comparison                         │   │
│  │  - Generates structured change log                   │   │
│  │  - Categorizes changes by severity                   │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Change Report Generator                             │   │
│  │  - Creates Excel change log sheet                    │   │
│  │  - Highlights critical changes                       │   │
│  │  - Trend analysis (improving/deteriorating)          │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Notification Service                                │   │
│  │  - Email alerts for critical changes                 │   │
│  │  - Slack/Teams integration                           │   │
│  │  - Configurable thresholds                           │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**Change Detection Categories:**

```python
class ChangeCategory:
    CRITICAL = "critical"      # Milestone date slips >10 days, critical path changes
    HIGH = "high"              # Activity date changes >5 days, new critical activities
    MEDIUM = "medium"          # Activity name changes, logic changes
    LOW = "low"                # Description updates, activity code changes
    INFO = "info"              # New activities added, completed activities

class ChangeType:
    ACTIVITY_ADDED = "activity_added"
    ACTIVITY_DELETED = "activity_deleted"
    DATE_CHANGED = "date_changed"
    NAME_CHANGED = "name_changed"
    LOGIC_CHANGED = "logic_changed"
    RESOURCE_CHANGED = "resource_changed"
    STATUS_CHANGED = "status_changed"
    MILESTONE_SLIPPED = "milestone_slipped"
    CRITICAL_PATH_CHANGED = "critical_path_changed"
```

**Example Change Report:**

```
═══════════════════════════════════════════════════════════════
P6 SCHEDULE CHANGE REPORT
═══════════════════════════════════════════════════════════════
Project: Glendale Public Storage Development
Previous Update: 2026-01-28 06:00 AM
Current Update: 2026-01-30 06:00 AM
Changes Detected: 23

🔴 CRITICAL CHANGES (3)
───────────────────────────────────────────────────────────────
1. MILESTONE SLIP: 90% CDs Complete
   - Previous Date: 02/10/2026
   - New Date: 02/15/2026
   - Variance: +5 days
   - Impact: Delays Building Permit Submittal
   - On Critical Path: YES

2. ACTIVITY ADDED TO CRITICAL PATH: SUB-002
   - Activity: MEP Coordination Drawings
   - Total Float: 0 days (was 5 days)
   - Status: Not Started (OVERDUE by 29 days)
   - Impact: HIGH - blocking permit

3. CRITICAL PATH LENGTH INCREASED
   - Previous: 245 days
   - Current: 250 days
   - Change: +5 days
   - Project Completion: 11/01/2027 (was 10/27/2027)

🟡 HIGH PRIORITY CHANGES (5)
───────────────────────────────────────────────────────────────
4. DATE CHANGE: Site Mobilization (SITE-1010)
   - Start Date: 02/01/2026 → 02/03/2026 (+2 days)
   - Finish Date: 02/05/2026 → 02/07/2026 (+2 days)
   - Float: 10 days

5. NEW ACTIVITY ADDED: Environmental Inspection (ENV-105)
   - Start Date: 02/15/2026
   - Duration: 3 days
   - Predecessor: Clearing & Grubbing
   - Impact: May affect excavation start

[... 3 more high priority changes ...]

🟢 MEDIUM PRIORITY CHANGES (8)
───────────────────────────────────────────────────────────────
[... activity name changes, description updates ...]

ℹ️  INFORMATIONAL CHANGES (7)
───────────────────────────────────────────────────────────────
[... completed activities, minor updates ...]

═══════════════════════════════════════════════════════════════
RECOMMENDATIONS
═══════════════════════════════════════════════════════════════
1. Immediate attention required on SUB-002 (MEP Drawings)
2. Review 90% CDs milestone recovery plan
3. Coordinate with environmental inspector for new requirement
4. Update stakeholder communications with new completion date

═══════════════════════════════════════════════════════════════
```

**Notification Example (Slack):**

```
🚨 P6 Schedule Update Alert

Project: Glendale Public Storage
Update: 2026-01-30 06:00 AM

🔴 3 Critical Changes Detected
🟡 5 High Priority Changes

Top Issues:
• 90% CDs milestone slipped +5 days
• Critical path extended to 250 days
• Project completion now 11/01/2027

View full report: [Dashboard Link]
```

**Pros:**
✅ Automated change detection  
✅ Detailed change reports  
✅ Proactive notifications  
✅ Works with any P6 version  
✅ No database access required  
✅ Moderate complexity  

**Cons:**
❌ Still requires XER export (manual or scheduled)  
❌ Not real-time (depends on export frequency)  
❌ File management overhead  

**Best For:** Most organizations - good balance of automation and simplicity

---

## Recommended Implementation Strategy

### Phase 1: Foundation (Immediate)
**Approach:** Manual XER Upload + Change Detection

**Deliverables:**
- XER diff engine
- Change log generation
- Dashboard with change history sheet

**Timeline:** Week 1-2

---

### Phase 2: Automation (Short-term)
**Approach:** Automated XER Export + File Monitoring

**Deliverables:**
- File watcher service
- Automated dashboard regeneration
- Email/Slack notifications

**Requirements:**
- P6 Job Service configuration (if available)
- Network share or cloud storage
- Notification service integration

**Timeline:** Week 3-4

---

### Phase 3: Real-Time Integration (Long-term)
**Approach:** P6 API Integration (if EPPM available)

**Deliverables:**
- P6 REST API connector
- Real-time change listener
- Incremental dashboard updates
- Webhook support

**Requirements:**
- P6 EPPM with API access
- API credentials and permissions
- Network connectivity

**Timeline:** Month 2-3

---

### Phase 4: Enterprise Integration (Optional)
**Approach:** Direct Database Connection or Integration API

**Deliverables:**
- Database triggers for change tracking
- Real-time event processing
- Multi-project dashboard
- Advanced analytics

**Requirements:**
- DBA access or Integration API license
- Security approvals
- Java middleware (if using Integration API)

**Timeline:** Month 4-6

---

## Change Detection Implementation

### Core Algorithm

```python
class XERDiffEngine:
    def __init__(self, previous_xer_path, current_xer_path):
        self.previous = self.parse_xer(previous_xer_path)
        self.current = self.parse_xer(current_xer_path)
        self.changes = []
    
    def detect_all_changes(self):
        """Detect all types of changes"""
        self.detect_activity_changes()
        self.detect_milestone_changes()
        self.detect_logic_changes()
        self.detect_critical_path_changes()
        self.detect_resource_changes()
        
        return self.categorize_changes()
    
    def detect_activity_changes(self):
        """Detect activity-level changes"""
        prev_activities = {a.id: a for a in self.previous.activities}
        curr_activities = {a.id: a for a in self.current.activities}
        
        # Added activities
        for act_id in curr_activities:
            if act_id not in prev_activities:
                self.changes.append({
                    'type': ChangeType.ACTIVITY_ADDED,
                    'category': ChangeCategory.INFO,
                    'activity_id': act_id,
                    'activity_name': curr_activities[act_id].name,
                    'details': f"New activity added: {curr_activities[act_id].name}"
                })
        
        # Deleted activities
        for act_id in prev_activities:
            if act_id not in curr_activities:
                self.changes.append({
                    'type': ChangeType.ACTIVITY_DELETED,
                    'category': ChangeCategory.MEDIUM,
                    'activity_id': act_id,
                    'activity_name': prev_activities[act_id].name,
                    'details': f"Activity deleted: {prev_activities[act_id].name}"
                })
        
        # Modified activities
        for act_id in curr_activities:
            if act_id in prev_activities:
                prev_act = prev_activities[act_id]
                curr_act = curr_activities[act_id]
                
                # Date changes
                if prev_act.start_date != curr_act.start_date:
                    variance_days = (curr_act.start_date - prev_act.start_date).days
                    category = self.categorize_date_change(variance_days, curr_act.is_milestone)
                    
                    self.changes.append({
                        'type': ChangeType.DATE_CHANGED,
                        'category': category,
                        'activity_id': act_id,
                        'activity_name': curr_act.name,
                        'field': 'start_date',
                        'old_value': prev_act.start_date,
                        'new_value': curr_act.start_date,
                        'variance_days': variance_days,
                        'details': f"Start date changed: {prev_act.start_date} → {curr_act.start_date} ({variance_days:+d} days)"
                    })
                
                # Name changes
                if prev_act.name != curr_act.name:
                    self.changes.append({
                        'type': ChangeType.NAME_CHANGED,
                        'category': ChangeCategory.MEDIUM,
                        'activity_id': act_id,
                        'old_value': prev_act.name,
                        'new_value': curr_act.name,
                        'details': f"Name changed: '{prev_act.name}' → '{curr_act.name}'"
                    })
    
    def categorize_date_change(self, variance_days, is_milestone):
        """Categorize date change by severity"""
        if is_milestone:
            if abs(variance_days) > 10:
                return ChangeCategory.CRITICAL
            elif abs(variance_days) > 5:
                return ChangeCategory.HIGH
            else:
                return ChangeCategory.MEDIUM
        else:
            if abs(variance_days) > 10:
                return ChangeCategory.HIGH
            elif abs(variance_days) > 5:
                return ChangeCategory.MEDIUM
            else:
                return ChangeCategory.LOW
    
    def detect_critical_path_changes(self):
        """Detect critical path changes"""
        prev_critical = set(a.id for a in self.previous.activities if a.total_float <= 0)
        curr_critical = set(a.id for a in self.current.activities if a.total_float <= 0)
        
        # Activities added to critical path
        newly_critical = curr_critical - prev_critical
        for act_id in newly_critical:
            act = self.current.get_activity(act_id)
            self.changes.append({
                'type': ChangeType.CRITICAL_PATH_CHANGED,
                'category': ChangeCategory.CRITICAL,
                'activity_id': act_id,
                'activity_name': act.name,
                'details': f"Activity added to critical path: {act.name} (float: {act.total_float} days)"
            })
        
        # Activities removed from critical path
        no_longer_critical = prev_critical - curr_critical
        for act_id in no_longer_critical:
            act = self.current.get_activity(act_id)
            self.changes.append({
                'type': ChangeType.CRITICAL_PATH_CHANGED,
                'category': ChangeCategory.INFO,
                'activity_id': act_id,
                'activity_name': act.name,
                'details': f"Activity removed from critical path: {act.name} (float: {act.total_float} days)"
            })
```

---

## Configuration

```json
{
  "change_tracking": {
    "enabled": true,
    "mode": "file_monitor",
    
    "file_monitor": {
      "watch_directory": "\\\\network\\p6_exports",
      "poll_interval_seconds": 300,
      "file_pattern": "*.xer",
      "archive_previous_versions": true,
      "archive_directory": "\\\\network\\p6_exports\\archive"
    },
    
    "change_detection": {
      "track_activity_additions": true,
      "track_activity_deletions": true,
      "track_date_changes": true,
      "track_name_changes": true,
      "track_logic_changes": true,
      "track_resource_changes": true,
      "track_critical_path_changes": true,
      
      "thresholds": {
        "critical_variance_days": 10,
        "high_variance_days": 5,
        "medium_variance_days": 2
      }
    },
    
    "notifications": {
      "enabled": true,
      "channels": ["email", "slack"],
      
      "email": {
        "recipients": ["scheduler@company.com", "pm@company.com"],
        "send_on_critical_only": false,
        "include_change_report": true
      },
      
      "slack": {
        "webhook_url": "https://hooks.slack.com/services/...",
        "channel": "#project-updates",
        "mention_on_critical": "@channel"
      }
    },
    
    "api_integration": {
      "enabled": false,
      "type": "rest",
      "base_url": "https://p6.company.com/api",
      "auth_type": "oauth2",
      "poll_interval_minutes": 15
    },
    
    "database_integration": {
      "enabled": false,
      "type": "oracle",
      "connection_string": "oracle://user:pass@host:1521/service",
      "read_only": true,
      "use_triggers": false
    }
  }
}
```

---

## Security Considerations

### File-Based Approaches
- **Network Share Permissions:** Ensure SixTerminal has read-only access
- **File Encryption:** Consider encrypting XER files in transit
- **Access Logging:** Track who accesses exported files

### API Integration
- **Authentication:** Use OAuth 2.0 or API keys (not basic auth)
- **API Key Storage:** Store in environment variables, not code
- **Rate Limiting:** Respect P6 API rate limits
- **Read-Only Access:** Request minimum necessary permissions

### Database Integration
- **Read-Only User:** Create dedicated read-only database user
- **Network Security:** Use VPN or secure connection
- **Audit Logging:** Log all database queries
- **No Direct Writes:** Never write directly to P6 tables

---

## Conclusion

The optimal approach depends on your organization's infrastructure and requirements:

**For Most Users:** Start with **Approach 6 (Hybrid File Monitor + Change Detection)**
- Good balance of automation and simplicity
- Works with any P6 version
- Provides detailed change tracking
- Can be enhanced later with API integration

**For P6 EPPM Users:** Implement **Approach 3 (P6 API Integration)**
- Near real-time updates
- Official supported method
- Scalable to multiple projects

**For Enterprise:** Consider **Approach 4 (Database Integration)** with proper approvals
- Real-time change detection
- Most comprehensive data access
- Requires significant security review

**Start Simple, Enhance Later:** Begin with manual XER upload and change detection, then add automation as needed. This allows you to validate the dashboard design before investing in complex integration.

---

## Next Steps

1. **Review this document** with your team and P6 administrator
2. **Determine which approach** fits your organization's infrastructure
3. **Obtain necessary approvals** (API access, database access, etc.)
4. **Implement Phase 1** (manual upload + change detection) first
5. **Iterate and enhance** based on user feedback

The change tracking system will make SixTerminal a living dashboard that automatically stays in sync with your P6 schedule, dramatically reducing manual effort while improving stakeholder communication.
