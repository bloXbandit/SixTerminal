from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class ScheduleCopilot:
    """
    The Brain 🧠
    Interacts with the P6Parser and Analyzer to answer natural language questions.
    Designed to work with OpenAI/Gemini Function Calling.
    """
    
    def __init__(self, parser, analyzer):
        self.parser = parser
        self.analyzer = analyzer
        self.context = {}

    def build_system_prompt(self) -> str:
        """
        Creates the 'Soul' of the P6 Copilot.
        Injects the current schedule health metrics into the prompt
        so the AI is immediately aware of the project state.
        """
        # Grab live data
        metrics = self.parser.get_llm_context()['project_metrics']
        
        prompt = f"""You are the SixTerminal AI Copilot, an expert Construction Scheduler.
You have access to the live P6 schedule data for this project.

CURRENT PROJECT STATUS:
- Total Activities: {metrics['total_activities']}
- Completion: {metrics['completed']} completed, {metrics['in_progress']} in progress.
- Project Dates: {metrics['project_start']} to {metrics['project_finish']}

YOUR GOAL:
Help the user analyze delays, find critical path issues, and understand the stairway chart.
Answer concisely. If a user asks about a specific activity, use the 'lookup_activity' tool.
"""
        return prompt

    def query(self, user_input: str):
        """
        This is where we would hook into the actual LLM API.
        For the prototype, this will simulate the routing.
        """
        # TODO: Implement actual LLM call with tool definitions
        pass

    # --- TOOLS FOR THE AI ---
    
    def tool_lookup_activity(self, activity_id: str):
        """AI Tool: Get details for a specific Activity ID"""
        # Logic to search df_activities
        pass

    def tool_get_critical_path(self):
        """AI Tool: List top 10 critical path activities"""
        pass
