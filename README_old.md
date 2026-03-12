# SixTerminal - P6 Stairway Tracker

**Transform Primavera P6 schedules into elegant, actionable Excel dashboards with AI-powered insights.**

---

## Overview

SixTerminal (P6 Stairway Tracker) is a Python-based tool designed for master project schedulers who need to communicate complex P6 schedule data to stakeholders in a clear, visual format. The application automatically extracts data from XER files and generates professional Excel dashboards with multiple specialized views.

### Key Features

🎯 **Stairway Visualization** - Unique milestone tracker showing baseline vs current progression  
📊 **Multi-View Dashboards** - Executive summary, milestones, procurement, punchlist, lookahead  
🤖 **AI Copilot** - Natural language interface to query and analyze schedule data  
⚡ **Fast Processing** - Handles 1000+ activity schedules in under 30 seconds  
🎨 **Professional Formatting** - Automated color-coding, conditional formatting, variance analysis  
🔄 **Repeatable** - Generate consistent reports with a single command  

---

## Project Status

**Current Phase:** Planning & Design  
**Target Release:** Q1 2026

This repository contains the comprehensive planning documents for the P6 Stairway Tracker application. Development will begin following the roadmap outlined in the planning documentation.

---

## Documentation

📋 **[P6 Stairway Tracker Planning Document](./docs/P6_Stairway_Tracker_Planning_Document.md)**  
Complete system design, architecture, dashboard specifications, and implementation roadmap.

🤖 **[AI Copilot Integration Specification](./docs/AI_Copilot_Integration.md)**  
Detailed technical specification for the AI-powered natural language interface.

---

## What Problem Does This Solve?

Master project schedulers spend hours each week:
- Manually exporting P6 data to Excel
- Creating stakeholder-friendly summaries
- Tracking milestone slippage across schedule updates
- Identifying critical procurement items
- Formatting reports for consistency

**SixTerminal automates this entire workflow**, transforming XER files into polished dashboards in seconds.

---

## Dashboard Views

### 1. Executive Summary
High-level project health with KPIs, critical issues, and upcoming milestones.

### 2. Milestone Tracker (Stairway Chart)
Visual timeline showing baseline vs current milestone progression, making schedule slippage instantly visible.

### 3. Material & Procurement Tracker
Consolidated view of submittals, long-lead equipment, and material deliveries.

### 4. Punchlist & Closeout Tracker
Final completion activities, inspections, and project closeout deliverables.

### 5. Schedule Log & Change History
Documentation of schedule changes, variance analysis, and critical path evolution.

### 6. Lookahead View
Upcoming activities in 30/60/90-day windows for field planning and coordination.

---

## AI Copilot

The integrated AI assistant allows users to interact with schedule data using natural language:

```
User: "What activities are behind schedule?"
AI: "I found 5 activities behind schedule:
     🔴 DES-1050: 35% Design Review (+15 days)
     🔴 SUB-002: MEP Coordination Drawings (+29 days, CRITICAL)
     ..."

User: "What's the next critical milestone?"
AI: "90% Construction Documents Complete on 02/15/2026
     Status: 🟡 At Risk (18 days away, 5 days float)"
```

**Features:**
- Natural language queries in plain English
- Proactive insights and risk identification
- Trend analysis across schedule updates
- Recovery strategy suggestions
- Cost-effective (~$0.01 per conversation)

---

## Technology Stack

**Core:**
- Python 3.11+
- xerparser (XER file parsing)
- openpyxl (Excel generation)
- pandas (data analysis)

**AI Integration:**
- OpenAI GPT-4.1-mini / Google Gemini-2.5-flash
- Function calling for structured data access
- CLI and web interface options

---

## Roadmap

### Phase 1: Foundation (Weeks 1-2)
- XER parsing and data extraction
- Core data processing and analytics
- Basic Excel generation

### Phase 2: Dashboard Development (Weeks 2-3)
- Implement all 6 dashboard sheets
- Apply formatting and conditional logic
- Generate embedded visualizations

### Phase 3: AI Integration (Weeks 3-4)
- Function library for schedule queries
- CLI chat interface
- Proactive insights generation

### Phase 4: Polish & Testing (Week 4)
- Performance optimization
- Documentation and examples
- Real-world testing with sample schedules

---

## Target Users

- **Master Project Schedulers** - Primary users who generate reports
- **Project Managers** - Stakeholders who need schedule insights
- **Executives** - High-level project health monitoring
- **Contractors** - Field planning and lookahead coordination
- **Owners** - Milestone tracking and procurement oversight

---

## Design Principles

1. **Visual Clarity** - Information should be scannable in seconds
2. **Automated Intelligence** - Let the software do the analysis
3. **Stakeholder Focus** - Different views for different audiences
4. **Consistency** - Repeatable, professional output every time
5. **Simplicity** - Powerful features with simple interface

---

## Contributing

This project is currently in the planning phase. Contributions, feedback, and suggestions are welcome!

---

## License

TBD

---

## Contact

For questions or collaboration opportunities, please open an issue in this repository.

---

## Acknowledgments

Built with insights from master project schedulers in the construction industry who understand the challenges of communicating complex schedule data to diverse stakeholders.

**Powered by Manus AI** - Intelligent automation for project management.
