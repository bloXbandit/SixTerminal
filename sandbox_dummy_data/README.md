# Sandbox Dummy Data Framework
Use these files to test all 3 LLM tiers without exposing real company data.

## Folder Structure
```
sandbox_dummy_data/
├── employee_hub/          ← Tier 1: Employee Assistant
│   ├── pto_policy.md
│   ├── training_resources.md
│   └── bonus_policy.md
├── project_alpha/         ← Tier 2: Project Assistant
│   ├── contract_summary.md
│   ├── meeting_transcript_001.md
│   └── schedule_summary.md
└── executive/             ← Tier 3: God Mode
    ├── corporate_charter.md
    ├── growth_targets_q4.md
    └── exec_meeting_transcript.md
```

## Test Questions Per Tier

### Tier 1 — Employee
- "How many PTO days do I get after 2 years?"
- "What training is available for a PSP?"
- "When are bonuses paid out?"

### Tier 2 — Project
- "What is the agreement with the city on Project Alpha?"
- "What were the action items from the last meeting?"
- "Is the schedule on track?"

### Tier 3 — God Mode
- "What were the Q4 growth targets discussed by the exec team?"
- "How many employees were hired last quarter?"
- "What does the corporate charter say about decision authority?"
