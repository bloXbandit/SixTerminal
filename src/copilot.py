import openai
import os
from typing import Dict, Any, List
import pandas as pd
import json
import logging
from config import config

logger = logging.getLogger(__name__)

class ScheduleCopilot:
    """
    Real implementation of the AI Copilot.
    Uses OpenAI (or compatible) API to answer schedule questions.
    """
    
    def __init__(self, parser, analyzer):
        self.parser = parser
        self.analyzer = analyzer
        self.client = None
        self._setup_client()

    def _setup_client(self):
        """Initialize OpenAI client with config settings."""
        api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
        base_url = config.get("api_base_url")
        
        if api_key:
            self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        else:
            logger.warning("No API Key found for AI Copilot.")

    def query(self, user_input: str, chat_history: List[Dict] = []) -> str:
        """
        Send user query + context to LLM and get a response.
        """
        if not self.client:
            return "⚠️ AI Config Error: Please set your API Key in Settings."

        # 1. Build Context (The "Health Stats")
        context_data = self.parser.get_llm_context()
        project_info = context_data.get('project_info', {})
        metrics = context_data.get('project_metrics', {})
        wbs_phases = context_data.get('wbs_phases', [])
        critical_stats = context_data.get('critical_stats', {})
        
        # Get critical path data with available columns
        crit_path_df = self.analyzer.get_critical_path().head(5)
        if not crit_path_df.empty:
            # Only include columns that exist
            available_cols = []
            for col in ['task_code', 'task_name', 'total_float_hr_cnt']:
                if col in crit_path_df.columns:
                    available_cols.append(col)
            
            if available_cols:
                critical_path = crit_path_df[available_cols].to_dict('records')
            else:
                critical_path = []
        else:
            critical_path = []
        
        # Format phases for prompt
        phases_str = ", ".join(wbs_phases[:5]) + ("..." if len(wbs_phases) > 5 else "")
        
        system_prompt = f"""
        You are '6ix Copilot', an expert Senior Construction Scheduler and Project Controls Manager.
        Your goal is to tell the "story" of the schedule, not just report numbers.
        
        CONTEXT:
        You are analyzing the project: "{project_info.get('name', 'Unknown')}"
        Current Data Date: {project_info.get('data_date', 'Unknown')}
        
        PROJECT VITALS:
        - Progress: {metrics.get('percent_complete', '0%')} Complete
        - Activity Counts: {metrics.get('completed', 0)} Done | {metrics.get('in_progress', 0)} Active | {metrics.get('not_started', 0)} Pending
        - Critical Activities: {critical_stats.get('critical_count', 0)} tasks with zero or negative float
        - Key Phases (WBS): {phases_str}
        
        CRITICAL PATH (Top 5 Drivers):
        {json.dumps(critical_path, indent=2) if critical_path else 'No critical path data available'}
        
        NARRATIVE INSTRUCTIONS:
        1. **Construct a Story**: When asked about status, don't just list stats. Weave them into a narrative. 
           (e.g., "We are currently 45% complete, with the main focus shifting from Foundation to Steel Erection...")
        2. **Contextualize Dates**: Use the Data Date ({project_info.get('data_date', 'Unknown')}) as "today". Speak about "past" and "future" relative to this date.
        3. **Explain "Why"**: If critical path count is high, explain that the project has zero flexibility.
        4. **Be Proactive**: If you see critical tasks, warn the user about specific delays.
        5. **Tone**: Professional, authoritative, yet conversational (like a Site Superintendent).
        
        If asked general questions ("Hi", "Help"), be brief and friendly.
        If asked specific schedule questions, use the data above to back up your narrative.
        """

        messages = [{"role": "system", "content": system_prompt}] + chat_history + [{"role": "user", "content": user_input}]

        try:
            response = self.client.chat.completions.create(
                model=config.get("ai_model", "gpt-4-turbo"),
                messages=messages,
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"❌ AI Error: {str(e)}"
