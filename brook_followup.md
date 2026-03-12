# Follow-Up: LLM Implementation Plan
**To:** Brook Bolger  
**From:** Kenneth Manjo  
**Re:** LLM Scope — Delivery Framework

---

Hi Brook,

After reviewing the scope and our conversation, here's a clear picture of what we can deliver across all three tiers — and what I need to move forward.

---

## What We're Building

### Tier 1 — Employee Assistant
- Employees ask plain-English questions about HR policies, training, benefits
- Answers pull directly from the Employee Hub on SharePoint
- Cites the exact document and section so employees can verify
- Example: *"How many PTO days do I get after 2 years?"* → instant answer with source

### Tier 2 — Project Assistant *(already prototyped in Stelic Insights)*
- Project team asks questions about their specific project files, schedules, contracts
- Understands document revisions — knows when a new version supersedes an old one
- Connects to Teams: joins meetings via bot, stores transcripts automatically in the project folder
- Example: *"What's the agreement with Southern California Edison?"* → answer with doc + page citation

### Tier 3 — God Mode (Executive)
- Executives ask cross-company questions across all projects, financials, and corporate documents
- Access-controlled — only available to approved exec accounts
- Example: *"What were our growth targets discussed in Q4?"* → pulls from exec Teams chat + documents

---

## The Flow (Non-Technical)

```
Employee logs in → System checks their role → Pulls only what they're allowed to see
→ Finds the most relevant documents → AI answers in plain English with citations
```

One AI at the end. Smart routing and security in the middle.

---

## What I Need to Get Started

To build and test this without touching live systems, I need:

1. **Access to test SharePoint folders** — Employee Hub + one pilot project folder (e.g., GDOT I-285)
2. **A test Teams environment** — so I can validate the meeting bot and transcript storage
3. **An Azure App Registration** — this is what allows our system to securely read Microsoft data (IT or Dashboard Solutions can create this; it's standard for any Microsoft integration)
4. **A hosting environment** — the AI Sandbox in Fabric/Power BI works for the dashboard layer; I'll need a small Azure App Service slot for the backend (Dashboard Solutions may already have this provisioned)

---

## Suggested Next Step

I'd recommend a 30-minute call with Dashboard Solutions to confirm what infrastructure is already in place — they likely have pieces of this built for the Power BI connectors. That avoids duplication and gets us moving faster.

Happy to set that up if helpful.

Best regards,  
Kenneth Manjo
