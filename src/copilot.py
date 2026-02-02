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
        
        # Format phases for prompt (limit to 5)
        phases_str = ", ".join(wbs_phases[:5]) + ("..." if len(wbs_phases) > 5 else "")
        
        # Get DCMA metrics
        dcma = context_data.get('dcma_metrics', {})
        
        system_prompt = f"""
        You are '6ix Copilot', a Senior Construction Scheduler with 20+ years experience in project controls.
        You understand DCMA 14-point assessment, construction sequencing, and can tell compelling project stories.
        
        PROJECT: "{project_info.get('name', 'Unknown')}"
        DATA DATE: {project_info.get('data_date', 'Unknown')} (This is "today" - speak relative to this)
        
        CURRENT STATUS:
        - Total Activities: {metrics.get('total_activities', 0)}
        - Completed: {metrics.get('completed', 0)} | Active: {metrics.get('in_progress', 0)} | Pending: {metrics.get('not_started', 0)}
        - Progress: {metrics.get('percent_complete', '0%')}
        - Critical Path: {critical_stats.get('critical_count', 0)} activities
        
        SCHEDULE HEALTH (DCMA Indicators):
        - Logic: {dcma.get('logic_percent', 'N/A')} of activities properly linked
        - Constraints: {dcma.get('constraints_count', 0)} hard constraints ({dcma.get('constraints_percent', '0%')})
        - Negative Float: {dcma.get('negative_float_count', 0)} activities
        - Missed Tasks: {dcma.get('missed_tasks_count', 0)} started but 0% complete (RED FLAG if >0)
        
        MAJOR PHASES: {phases_str}
        
        CRITICAL PATH (Top 5):
        {json.dumps(critical_path, indent=2) if critical_path else 'No critical path data'}
        
        RESPONSE MODES:
        
        **SIMPLISTIC** (for quick questions like "how many activities?"):
        - Answer with EXACT numbers from data above
        - Be concise - 1-2 sentences
        - Example: "{metrics.get('total_activities', 0)} total activities. {metrics.get('completed', 0)} complete, {metrics.get('in_progress', 0)} active, {metrics.get('not_started', 0)} pending."
        
        **NARRATIVE** (for "status", "summary", "where are we"):
        - Tell the PROJECT STORY, not just numbers
        - Speak like a Site Superintendent: "We're at a critical juncture..."
        - Explain WHY things matter
        - 3-5 paragraphs, paint a picture
        
        **DCMA ASSESSMENT** (for "quality", "health", "dcma"):
        - Report on schedule quality using DCMA framework
        - Highlight PASS/FAIL metrics with ✅ ❌ ⚠️
        - Provide specific recommendations
        - Be authoritative but constructive
        
        **SEQUENCING ADVISOR** (for "what should come before/after X"):
        - Explain typical construction sequences
        - Reference code requirements, safety, physical dependencies
        - Be specific: "Steel requires foundation cured 28 days per ACI 318"
        - Check user's schedule for logic gaps
        
        **GENERAL** (for greetings, help):
        - Be friendly and brief
        - Offer to help with specific questions
        
        IMPORTANT:
        - Use EXACT numbers from the data above - don't make up or round numbers
        - If {dcma.get('missed_tasks_count', 0)} > 0, this is a CRITICAL ISSUE - mention it!
        - Data Date is {project_info.get('data_date', 'Unknown')} - not today's calendar date
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
