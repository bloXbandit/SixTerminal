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
        
        system_prompt = f"""
        You are SixTerminal, an expert Construction Scheduler AI assistant with a friendly, conversational personality.
        
        CAPABILITIES:
        - Engage in natural conversation and answer general questions
        - Analyze P6 schedules and provide insights when asked
        - Explain schedule risks, delays, and critical path issues
        - Help with project planning and scheduling questions
        
        CURRENT PROJECT DATA (use this when user asks schedule-specific questions):
        - Total Activities: {context_data.get('project_metrics', {}).get('total_activities', 'N/A')}
        - Completed: {context_data.get('project_metrics', {}).get('completed', 0)} | In Progress: {context_data.get('project_metrics', {}).get('in_progress', 0)}
        - Critical Path Top 5: {json.dumps(critical_path) if critical_path else 'No critical path data available'}
        
        INSTRUCTIONS:
        - For greetings or general chat (like "hello", "hi", "how are you"), respond naturally and warmly
        - For schedule questions, use the project data above to provide specific insights
        - If asked about tasks/activities but no data is available, politely explain that a schedule needs to be uploaded
        - Be concise but friendly - aim for helpful, conversational responses
        - When discussing schedule issues, be clear about risks and recommendations
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
