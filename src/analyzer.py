import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class ScheduleAnalyzer:
    """
    The Brain 🧠
    Performs the heavy lifting of P6 schedule analysis.
    - Calculates variances (Baseline vs Current)
    - Identifies Critical Path (Float <= 0)
    - Categorizes status (On Track, At Risk, Critical)
    - Groups data for specific Dashboard views (Procurement, Milestones)
    """

    def __init__(self, parser):
        self.parser = parser
        self.df_main = None
        
        # Use actual data date from P6 XER, fallback to today
        if hasattr(parser, 'project_metadata') and parser.project_metadata.get('data_date'):
            self.analysis_date = parser.project_metadata['data_date']
            logger.info(f"Using P6 data date: {self.analysis_date}")
        else:
            self.analysis_date = datetime.now()
            logger.warning("P6 data date not found, using current date")
        
        self._prepare_analysis_dataset()

    def _prepare_analysis_dataset(self):
        """
        Merges and cleans raw parser tables into a master 'Analysis DataFrame'.
        This handles the P6 date logic (Actuals vs Early vs Late).
        """
        raw_tasks = self.parser.get_activities().copy()
        
        if raw_tasks.empty:
            logger.warning("No activities found in XER file")
            self.df_main = pd.DataFrame()
            return
        
        # Debug: log available columns
        logger.info(f"Available columns: {raw_tasks.columns.tolist()}")
        
        # Find the status column (could be status_code or status)
        status_col = None
        for col in ['status_code', 'status', 'task_status_code']:
            if col in raw_tasks.columns:
                status_col = col
                break
        
        # 1. Map P6 Status Codes to Human Readable
        status_map = {
            'TK_NotStart': 'Not Started',
            'TK_Active': 'In Progress',
            'TK_Complete': 'Completed'
        }
        
        if status_col:
            raw_tasks['status_readable'] = raw_tasks[status_col].map(status_map).fillna('Unknown')
        else:
            logger.warning("No status column found, defaulting to 'Unknown'")
            raw_tasks['status_readable'] = 'Unknown'
            status_col = 'status_readable'

        # 2. Define "Current Start" and "Current Finish" based on Status
        # P6 Logic:
        # - If Completed: Use Actual Start / Actual Finish
        # - If In Progress: Use Actual Start / Early Finish (Forecast)
        # - If Not Started: Use Early Start / Early Finish
        
        # Handle different possible column names
        early_start = 'early_start_date' if 'early_start_date' in raw_tasks.columns else 'target_start_date'
        early_end = 'early_end_date' if 'early_end_date' in raw_tasks.columns else 'target_end_date'
        act_start = 'act_start_date' if 'act_start_date' in raw_tasks.columns else early_start
        act_end = 'act_end_date' if 'act_end_date' in raw_tasks.columns else early_end
        
        if status_col and status_col in raw_tasks.columns:
            raw_tasks['current_start'] = np.where(
                raw_tasks[status_col] == 'TK_NotStart', 
                raw_tasks.get(early_start), 
                raw_tasks.get(act_start)
            )
            
            raw_tasks['current_finish'] = np.where(
                raw_tasks[status_col] == 'TK_Complete', 
                raw_tasks.get(act_end), 
                raw_tasks.get(early_end)
            )
        else:
            raw_tasks['current_start'] = raw_tasks.get(early_start)
            raw_tasks['current_finish'] = raw_tasks.get(early_end)

        # 3. Calculate Variance (vs Target/Baseline)
        # Note: 'target_end_date' in TASK table usually maps to Project Baseline if assigned.
        if 'target_end_date' in raw_tasks.columns:
            # Variance = Current Finish - Baseline Finish
            # Positive days = Late (Slippage)
            # Negative days = Early (Gain)
            
            # Ensure datetime types
            raw_tasks['current_finish'] = pd.to_datetime(raw_tasks['current_finish'])
            raw_tasks['target_end_date'] = pd.to_datetime(raw_tasks['target_end_date'])
            
            # Calculate diff in days
            raw_tasks['variance_days'] = (raw_tasks['current_finish'] - raw_tasks['target_end_date']).dt.days
            raw_tasks['variance_days'] = raw_tasks['variance_days'].fillna(0) # No baseline = 0 variance
        else:
            raw_tasks['variance_days'] = 0

        # 4. Critical Path Flag
        # Standard P6 definition: Total Float <= 0 hours
        # P6 stores float in hours usually.
        if 'total_float_hr_cnt' in raw_tasks.columns:
            raw_tasks['is_critical'] = raw_tasks['total_float_hr_cnt'] <= 0
        else:
            raw_tasks['is_critical'] = False

        self.df_main = raw_tasks
        logger.info(f"Analysis Dataset Prepared. {len(self.df_main)} activities processed.")

    def get_critical_path(self) -> pd.DataFrame:
        """Returns only critical path activities, sorted by date."""
        if self.df_main is None or self.df_main.empty:
            return pd.DataFrame()
        
        if 'is_critical' not in self.df_main.columns:
            logger.warning("No is_critical column found, returning empty critical path")
            return pd.DataFrame()
        
        crit = self.df_main[self.df_main['is_critical']].copy()
        
        if not crit.empty and 'current_start' in crit.columns:
            return crit.sort_values(by='current_start')
        return crit

    def get_milestones(self) -> pd.DataFrame:
        """
        Extracts milestones using multiple detection methods:
        1. P6 task_type (TT_Mile, TT_MileStart)
        2. Zero duration activities
        3. Task code contains 'MIL' or 'MILE'
        4. Task name contains 'milestone'
        """
        if self.df_main is None or self.df_main.empty:
            return pd.DataFrame()
        
        # Initialize mask with all False
        mask = pd.Series([False] * len(self.df_main), index=self.df_main.index)
        
        # Method 1: Check task_type for milestone types
        if 'task_type' in self.df_main.columns:
            type_mask = self.df_main['task_type'].isin(['TT_Mile', 'TT_MileStart'])
            mask = mask | type_mask
            logger.info(f"Found {type_mask.sum()} milestones by task_type")
        
        # Method 2: Zero duration activities (common milestone indicator)
        if 'target_drtn_hr_cnt' in self.df_main.columns:
            zero_dur_mask = self.df_main['target_drtn_hr_cnt'] == 0
            mask = mask | zero_dur_mask
            logger.info(f"Found {zero_dur_mask.sum()} milestones by zero duration")
        
        # Method 3: Task code contains milestone keywords (universal patterns)
        # Matches: MIL-, MILE-, MS-, M-, milestone codes
        if 'task_code' in self.df_main.columns:
            code_patterns = r'(^MIL[E]?[-_]|^MS[-_]|^M[-_]\d)'
            code_mask = self.df_main['task_code'].str.contains(code_patterns, case=False, na=False, regex=True)
            mask = mask | code_mask
            logger.info(f"Found {code_mask.sum()} milestones by task_code pattern")
        
        # Method 4: Task name contains 'milestone'
        if 'task_name' in self.df_main.columns:
            name_mask = self.df_main['task_name'].str.contains('milestone', case=False, na=False)
            mask = mask | name_mask
            logger.info(f"Found {name_mask.sum()} milestones by task_name")
        
        milestones = self.df_main[mask].copy()
        logger.info(f"Total unique milestones detected: {len(milestones)}")
        
        if not milestones.empty and 'current_finish' in milestones.columns:
            return milestones.sort_values(by='current_finish')
        return milestones

    def get_procurement_log(self) -> pd.DataFrame:
        """
        Filters MAJOR Material/Procurement/Deliveries ONLY.
        Focus on high-value, long-lead procurement items:
        - Structural materials (steel, precast, concrete)
        - Building envelope (curtainwall, terracotta, glass)
        - Major MEP equipment and systems
        - Performance mock-ups
        
        Excludes: Small hardware, accessories, submittals, and minor components
        """
        if self.df_main is None or self.df_main.empty:
            return pd.DataFrame()
        
        if 'task_name' not in self.df_main.columns:
            logger.warning("No task_name column found, returning empty procurement log")
            return pd.DataFrame()
        
        # Initialize mask
        mask = pd.Series([False] * len(self.df_main), index=self.df_main.index)
        
        # Method 1: Common procurement task code prefixes (universal patterns)
        # PMU = Performance Mock-Up, FAB = Fabrication, DEL = Delivery
        # PROC = Procurement, MAT = Materials, ORD = Orders
        # Note: PUR- excluded (often includes awards/bonds, not actual materials)
        if 'task_code' in self.df_main.columns:
            code_prefixes = r'^(PMU-|FAB-|DEL-|PROC-|MAT-|ORD-)'
            code_mask = self.df_main['task_code'].str.contains(code_prefixes, case=False, na=False, regex=True)
            mask = mask | code_mask
            logger.info(f"Found {code_mask.sum()} items by procurement task codes")
        
        # Method 2: MAJOR procurement keywords (very selective)
        # Only include phrases that clearly indicate procurement/fabrication/delivery
        major_materials = [
            # Explicit procurement phrases
            'material procurement', 'equipment procurement', 'long lead',
            'fabricate and deliver', 'material order', 'equipment order',
            # Major structural (only if not installation)
            'structural steel', 'precast', 'curtainwall',
            # Major equipment (only if not installation)
            'chiller', 'boiler', 'cooling tower', 'air handler',
            'transformer', 'switchgear', 'generator',
            'elevator', 'escalator'
        ]
        
        for keyword in major_materials:
            keyword_mask = self.df_main['task_name'].str.contains(keyword, case=False, na=False)
            if keyword_mask.sum() > 0:
                mask = mask | keyword_mask
                logger.info(f"Found {keyword_mask.sum()} items with '{keyword}'")
        
        # Method 3: Exclude everything that's NOT major procurement
        exclude_keywords = [
            # Submittals and approvals
            'submit', 'approval', 'review', 'prepare',
            # Awards and contracts (not actual materials)
            'award', 'bond', 'contract',
            # Construction activities
            'equipment pad', 'hoist', 'mobilize', 'dismantle', 'pour equipment',
            'demonstration', 'training', 'install', 'erect', 'construct',
            # Small hardware and accessories
            'escutcheon', 'hanger', 'support', 'damper', 'flex connector',
            'expansion loop', 'guide', 'anchor', 'flashing', 'thermostatic',
            'barometric', 'meter', 'vfd', 'strainer', 'hydrant', 'hose bibb',
            'grease trap', 'outlet box', 'hammer arrester', 'mixing valve',
            'pressure reducing', 'insulation', 'cable', 'duct construction',
            'material standard'
        ]
        exclude_pattern = '|'.join(exclude_keywords)
        exclude_mask = self.df_main['task_name'].str.contains(exclude_pattern, case=False, na=False)
        
        # Apply exclusions
        mask = mask & ~exclude_mask
        
        result = self.df_main[mask].copy()
        logger.info(f"Total TRUE procurement/material items detected: {len(result)}")
        
        if not result.empty and 'current_finish' in result.columns:
            return result.sort_values(by='current_finish')
        return result

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """
        Returns high-level metrics for the Executive Dashboard sheet.
        """
        if self.df_main is None or self.df_main.empty:
            return {
                "data_date": self.analysis_date.strftime('%Y-%m-%d'),
                "total_activities": 0,
                "critical_activities": 0,
                "slipping_activities": 0,
                "percent_critical": 0
            }
        
        total = len(self.df_main)
        
        # Handle missing is_critical column
        if 'is_critical' in self.df_main.columns:
            critical_count = len(self.df_main[self.df_main['is_critical']])
        else:
            critical_count = 0
        
        # Handle missing variance_days column
        if 'variance_days' in self.df_main.columns:
            slipping_count = len(self.df_main[self.df_main['variance_days'] > 5])
        else:
            slipping_count = 0
        
        return {
            "data_date": self.analysis_date.strftime('%Y-%m-%d'),
            "total_activities": total,
            "critical_activities": critical_count,
            "slipping_activities": slipping_count,
            "percent_critical": round((critical_count / total) * 100, 1) if total > 0 else 0
        }

    def get_current_month_activities(self, days_window=30) -> Dict[str, pd.DataFrame]:
        """
        Get activities grouped by time period relative to data date.
        Returns dict with 'last_month', 'this_month', 'next_month' DataFrames.
        
        Args:
            days_window: Number of days to look back/forward (default 30)
        """
        if self.df_main is None or self.df_main.empty:
            return {
                'last_month': pd.DataFrame(),
                'this_month': pd.DataFrame(),
                'next_month': pd.DataFrame()
            }
        
        from datetime import timedelta
        
        # Use data date or today
        data_date = self.analysis_date
        
        # Define time windows
        last_month_start = data_date - timedelta(days=days_window)
        next_month_end = data_date + timedelta(days=days_window)
        
        # LAST MONTH: Activities completed in last 30 days
        last_month_mask = (
            (self.df_main['status_code'] == 'TK_Complete') &
            (pd.notna(self.df_main['act_end_date'])) &
            (self.df_main['act_end_date'] >= last_month_start) &
            (self.df_main['act_end_date'] <= data_date)
        )
        last_month_df = self.df_main[last_month_mask].copy()
        
        # THIS MONTH: Activities that should be active now
        # Criteria: Started before data date AND finishing after data date OR currently active
        this_month_mask = (
            # Option 1: Activity spans the data date
            (
                (pd.notna(self.df_main['current_start'])) &
                (pd.notna(self.df_main['current_finish'])) &
                (self.df_main['current_start'] <= data_date) &
                (self.df_main['current_finish'] >= data_date)
            ) |
            # Option 2: Currently active status
            (self.df_main['status_code'] == 'TK_Active')
        )
        this_month_df = self.df_main[this_month_mask].copy()
        
        # NEXT MONTH: Activities starting in next 30 days
        next_month_mask = (
            (self.df_main['status_code'] == 'TK_NotStart') &
            (pd.notna(self.df_main['current_start'])) &
            (self.df_main['current_start'] > data_date) &
            (self.df_main['current_start'] <= next_month_end)
        )
        next_month_df = self.df_main[next_month_mask].copy()
        
        logger.info(f"Current Month Analysis: Last={len(last_month_df)}, This={len(this_month_df)}, Next={len(next_month_df)}")
        
        return {
            'last_month': last_month_df,
            'this_month': this_month_df,
            'next_month': next_month_df
        }
    
    def get_monthly_metrics(self, days_window=30) -> Dict[str, Any]:
        """
        Calculate monthly progress metrics.
        Returns summary statistics for current month focus.
        """
        month_data = self.get_current_month_activities(days_window)
        
        last_month = month_data['last_month']
        this_month = month_data['this_month']
        next_month = month_data['next_month']
        
        # This month planned completions (activities scheduled to finish this month)
        from datetime import timedelta
        data_date = self.analysis_date
        month_end = data_date + timedelta(days=days_window)
        
        planned_completions = 0
        actual_completions = 0
        
        if not this_month.empty:
            # Planned: activities with finish date this month
            planned_mask = (
                (pd.notna(this_month['current_finish'])) &
                (this_month['current_finish'] >= data_date) &
                (this_month['current_finish'] <= month_end)
            )
            planned_completions = planned_mask.sum()
            
            # Actual: activities already completed this month
            actual_mask = (
                (this_month['status_code'] == 'TK_Complete') &
                (pd.notna(this_month['act_end_date'])) &
                (this_month['act_end_date'] >= data_date)
            )
            actual_completions = actual_mask.sum()
        
        completion_rate = (actual_completions / planned_completions * 100) if planned_completions > 0 else 0
        
        # Critical activities this month
        critical_this_month = 0
        if not this_month.empty and 'total_float_hr_cnt' in this_month.columns:
            critical_this_month = len(this_month[this_month['total_float_hr_cnt'] <= 0])
        
        # Behind schedule (started but not progressing)
        behind_count = 0
        if not this_month.empty and 'complete_pct' in this_month.columns:
            behind_mask = (
                (this_month['status_code'] == 'TK_Active') &
                (this_month['complete_pct'] == 0)
            )
            behind_count = behind_mask.sum()
        
        return {
            'data_date': data_date.strftime('%Y-%m-%d'),
            'last_month_completed': len(last_month),
            'this_month_active': len(this_month),
            'next_month_starting': len(next_month),
            'planned_completions': planned_completions,
            'actual_completions': actual_completions,
            'completion_rate': round(completion_rate, 1),
            'critical_this_month': critical_this_month,
            'behind_schedule': behind_count
        }

    def get_schedule_health_metrics(self) -> Dict[str, Any]:
        """
        Extract P6 schedule log metrics - constraints, relationships, open-ended activities.
        Returns dict with schedule quality indicators.
        """
        if not hasattr(self.parser, 'reader') or not self.parser.reader:
            return {}
        
        xer = self.parser.reader
        
        # 1. Constraint Analysis
        constraint_types = {}
        for task_id, task in xer.tasks.items():
            if hasattr(task, 'cstr_type') and task.cstr_type:
                cstr_name = task.cstr_type.name if hasattr(task.cstr_type, 'name') else str(task.cstr_type)
                constraint_types[cstr_name] = constraint_types.get(cstr_name, 0) + 1
        
        total_constraints = sum(constraint_types.values())
        
        # 2. Relationship Analysis
        total_relationships = len(xer.relationships) if hasattr(xer, 'relationships') else 0
        
        rel_types = {}
        if hasattr(xer, 'relationships'):
            for rel_id, rel in xer.relationships.items():
                if hasattr(rel, 'pred_type'):
                    rel_name = rel.pred_type.name if hasattr(rel.pred_type, 'name') else str(rel.pred_type)
                    rel_types[rel_name] = rel_types.get(rel_name, 0) + 1
        
        # 3. Open-Ended Activities
        tasks_with_pred = set()
        tasks_with_succ = set()
        
        if hasattr(xer, 'relationships'):
            for rel_id, rel in xer.relationships.items():
                if hasattr(rel, 'task_id'):
                    tasks_with_pred.add(rel.task_id)
                if hasattr(rel, 'pred_task_id'):
                    tasks_with_succ.add(rel.pred_task_id)
        
        no_predecessors = len(xer.tasks) - len(tasks_with_pred)
        no_successors = len(xer.tasks) - len(tasks_with_succ)
        
        logger.info(f"Schedule Health: {total_constraints} constraints, {total_relationships} relationships, {no_predecessors} open starts, {no_successors} open ends")
        
        return {
            'total_constraints': total_constraints,
            'constraint_breakdown': constraint_types,
            'total_relationships': total_relationships,
            'relationship_breakdown': rel_types,
            'no_predecessors': no_predecessors,
            'no_successors': no_successors,
            'circular_relationships': 0  # Would require graph analysis - placeholder
        }
