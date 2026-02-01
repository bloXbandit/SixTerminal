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
        critical_path = self.analyzer.get_critical_path().head(5)[['task_code', 'task_name', 'total_float_hr_cnt']].to_dict('records')
        
        system_prompt = f"""
        You are an expert Construction Scheduler assistant named SixTerminal.
        
        CURRENT PROJECT DATA:
        - Activities: {context_data['project_metrics']['total_activities']}
        - Progress: {context_data['project_metrics']['completed']} completed / {context_data['project_metrics']['in_progress']} active.
        - Critical Path Top 5: {json.dumps(critical_path)}
        
        Your goal is to explain schedule risks concisely.
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
