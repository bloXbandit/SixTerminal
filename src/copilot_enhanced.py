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
    Enhanced AI Copilot - Master Scheduler Assistant
    
    Capabilities:
    - Accurate XER data extraction
    - DCMA 14-point assessment
    - Construction sequencing logic
    - Narrative storytelling
    - Role-based perspectives (GC, Sub, Owner, Scheduler)
    - Adaptive tone (simplistic to detailed)
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

    def _detect_query_mode(self, user_input: str) -> str:
        """
        Detect what kind of response the user wants.
        Returns: 'simplistic', 'narrative', 'dcma', 'sequencing', 'general'
        """
        user_lower = user_input.lower()
        
        # Simplistic mode - quick facts
        if any(keyword in user_lower for keyword in ['how many', 'count', 'number of', 'total']):
            return 'simplistic'
        
        # DCMA/Quality mode
        if any(keyword in user_lower for keyword in ['quality', 'dcma', 'health', 'assessment', 'metrics']):
            return 'dcma'
        
        # Sequencing mode
        if any(keyword in user_lower for keyword in ['before', 'after', 'sequence', 'order', 'predecessor', 'successor', 'should come']):
            return 'sequencing'
        
        # Narrative mode - status, story, summary
        if any(keyword in user_lower for keyword in ['status', 'summary', 'overview', 'story', 'tell me about', 'where are we']):
            return 'narrative'
        
        # General conversation
        return 'general'

    def _build_system_prompt(self, context: Dict[str, Any], mode: str) -> str:
        """
        Build dynamic system prompt based on detected mode.
        """
        project = context.get('project_identity', {})
        progress = context.get('progress', {})
        dcma = context.get('dcma_assessment', {})
        float_analysis = context.get('float_analysis', {})
        story = context.get('story_elements', {})
        wbs = context.get('wbs_phases', [])
        
        # Base identity (always included)
        base_prompt = f"""
You are '6ix Copilot', a Senior Construction Scheduler and Project Controls expert with 20+ years of experience.

PROJECT: {project.get('name', 'Unknown')}
TYPE: {project.get('type', 'Unknown')}
DATA DATE: {project.get('data_date', 'Unknown')} (This is "today" - speak relative to this date)

CURRENT STATUS:
- Total Activities: {progress.get('total_activities', 0)}
- Completed: {progress.get('completed', 0)} | Active: {progress.get('in_progress', 0)} | Pending: {progress.get('not_started', 0)}
- Progress: {progress.get('percent_complete', '0%')}
- Critical Path: {float_analysis.get('critical_count', 0)} activities ({float_analysis.get('critical_percent', '0%')})

MAJOR PHASES (WBS):
{', '.join(wbs[:5]) if wbs else 'No WBS data'}
"""
        
        # Mode-specific additions
        if mode == 'simplistic':
            return base_prompt + """
RESPONSE MODE: SIMPLISTIC
- Answer with EXACT numbers from the data above
- Be concise - 1-2 sentences max
- No storytelling, just facts
- Example: "6,495 total activities. 295 complete, 157 active, 6,043 pending."
"""
        
        elif mode == 'dcma':
            dcma_details = f"""
DCMA 14-POINT ASSESSMENT:
Score: {dcma.get('score', 'N/A')}

Key Metrics:
- Logic: {dcma.get('logic_percent', 'N/A')} connected {'✅ PASS' if dcma.get('logic_pass') else '❌ FAIL'}
- Constraints: {dcma.get('constraints_count', 0)} ({dcma.get('constraints_percent', '0%')}) {'✅ PASS' if dcma.get('constraints_pass') else '⚠️ WARNING'}
- Negative Float: {dcma.get('negative_float_count', 0)} {'✅ PASS' if dcma.get('negative_float_pass') else '❌ FAIL'}
- Missed Tasks: {dcma.get('missed_tasks_count', 0)} started but 0% complete {'✅ PASS' if dcma.get('missed_tasks_pass') else '❌ FAIL'}
- High Duration: {dcma.get('high_duration_count', 0)} activities >44 days {'✅ PASS' if dcma.get('high_duration_pass') else '⚠️ WARNING'}
- High Float: {dcma.get('high_float_count', 0)} activities >44 days float {'✅ PASS' if dcma.get('high_float_pass') else '⚠️ WARNING'}

RESPONSE MODE: DCMA ASSESSMENT
- Explain schedule quality using DCMA 14-point framework
- Highlight PASS/FAIL metrics
- Provide specific recommendations for failures
- Be authoritative but constructive
- Format with ✅ ❌ ⚠️ symbols for clarity
"""
            return base_prompt + dcma_details
        
        elif mode == 'sequencing':
            return base_prompt + """
RESPONSE MODE: SEQUENCING ADVISOR
- You are an expert in construction sequencing and logic
- Understand typical construction sequences:
  * Site: Survey → Demo → Excavation → Shoring → Foundation
  * Vertical: Foundation → Columns → Beams → Decking → MEP Rough
  * Envelope: Structure → Waterproofing → Cladding → Windows → Sealants
  * Interior: MEP Rough → Drywall → Paint → Flooring → Fixtures → Punch
  * MEP: Underground → Rough-In → Trim → Testing → Commissioning
- Explain WHY activities must be sequenced a certain way
- Reference code requirements, safety, or physical dependencies
- Be specific: "Steel erection requires foundation cured 28 days minimum per ACI 318"
- Check the user's schedule for logic gaps or incorrect sequencing
"""
        
        elif mode == 'narrative':
            narrative_context = f"""
STORY ELEMENTS:
- Current Phase: {story.get('current_phase', 'Unknown')}
- Recent Completions: {story.get('recent_completions_count', 0)} activities in last 30 days
- Behind Schedule: {story.get('behind_schedule_count', 0)} activities started but stalled
- Time Elapsed: {project.get('percent_time_elapsed', 'N/A')} of contract duration

RESPONSE MODE: NARRATIVE STORYTELLING
- Tell the PROJECT STORY, not just numbers
- Speak like a Site Superintendent giving a weekly update
- Use phrases like:
  * "We're at a critical juncture..."
  * "The team is focused on..."
  * "Here's what concerns me..."
  * "Bottom line is..."
- Contextualize dates relative to Data Date ({project.get('data_date')})
- Explain WHY things matter (e.g., "Steel is on critical path, any delay cascades")
- Be conversational but professional
- 3-5 paragraphs, paint a picture
"""
            return base_prompt + narrative_context
        
        else:  # general mode
            return base_prompt + """
RESPONSE MODE: GENERAL CONVERSATION
- For greetings ("hi", "hello"), be friendly and brief
- For general questions, provide helpful context
- If asked about specific schedule data, use the numbers above
- Be conversational and approachable
- Offer to help with more specific questions
"""

    def query(self, user_input: str, chat_history: List[Dict] = []) -> str:
        """
        Enhanced query method with mode detection and dynamic prompting.
        """
        if not self.client:
            return "⚠️ AI Config Error: Please set your API Key in Settings."

        try:
            # 1. Get enhanced context from parser
            context = self.parser.get_llm_context()
            
            # 2. Detect query mode
            mode = self._detect_query_mode(user_input)
            logger.info(f"Detected mode: {mode} for query: {user_input[:50]}...")
            
            # 3. Build dynamic system prompt
            system_prompt = self._build_system_prompt(context, mode)
            
            # 4. Add critical path details for reference
            crit_path_df = self.analyzer.get_critical_path().head(5)
            if not crit_path_df.empty:
                available_cols = []
                for col in ['task_code', 'task_name', 'total_float_hr_cnt']:
                    if col in crit_path_df.columns:
                        available_cols.append(col)
                
                if available_cols:
                    critical_path = crit_path_df[available_cols].to_dict('records')
                    system_prompt += f"\n\nCRITICAL PATH (Top 5):\n{json.dumps(critical_path, indent=2)}"
            
            # 5. Construct messages
            messages = [
                {"role": "system", "content": system_prompt}
            ] + chat_history + [
                {"role": "user", "content": user_input}
            ]
            
            # 6. Call OpenAI with appropriate temperature
            temperature = 0.2 if mode in ['simplistic', 'dcma'] else 0.4  # Lower temp for factual, higher for narrative
            
            response = self.client.chat.completions.create(
                model=config.get("ai_model", "gpt-4-turbo"),
                messages=messages,
                temperature=temperature
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"AI Query Error: {str(e)}")
            return f"❌ AI Error: {str(e)}"

    def get_activity_details(self, activity_id: str) -> Dict[str, Any]:
        """
        Helper function to get detailed info about a specific activity.
        Can be used for future function calling implementation.
        """
        df = self.parser.get_activities()
        activity = df[df['task_id'] == activity_id]
        
        if activity.empty:
            return {"error": "Activity not found"}
        
        return activity.iloc[0].to_dict()

    def get_predecessors(self, activity_id: str) -> List[Dict[str, Any]]:
        """
        Get all predecessors of an activity.
        For future function calling / sequencing analysis.
        """
        if self.parser.df_relationships is None:
            return []
        
        rels = self.parser.df_relationships
        preds = rels[rels['task_id'] == activity_id]
        
        return preds.to_dict('records')

    def get_successors(self, activity_id: str) -> List[Dict[str, Any]]:
        """
        Get all successors of an activity.
        For future function calling / sequencing analysis.
        """
        if self.parser.df_relationships is None:
            return []
        
        rels = self.parser.df_relationships
        succs = rels[rels['pred_task_id'] == activity_id]
        
        return succs.to_dict('records')
