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
        self.analysis_date = datetime.now() # Default, should ideally come from XER 'last_update_date'
        
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
        
        # Method 3: Task code contains milestone keywords
        if 'task_code' in self.df_main.columns:
            code_mask = self.df_main['task_code'].str.contains(r'MIL[E]?[-_]?\d', case=False, na=False, regex=True)
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
        Filters activities related to Material/Procurement/Deliveries.
        Detection methods:
        1. Keywords in task_name (submittal, procurement, deliver, order, etc.)
        2. Keywords in task_code (SUB-, PMU-, FAB-, etc.)
        """
        if self.df_main is None or self.df_main.empty:
            return pd.DataFrame()
        
        if 'task_name' not in self.df_main.columns:
            logger.warning("No task_name column found, returning empty procurement log")
            return pd.DataFrame()
        
        # Expanded keyword list based on analysis
        keywords = [
            'submittal', 'submit', 'procure', 'procurement', 'fabricat', 'fabrication',
            'deliver', 'delivery', 'order', 'purchase', 'approval', 'approve',
            'material', 'equipment', 'vendor', 'supplier', 'long lead',
            'rfp', 'rfi', 'shop drawing', 'sample'
        ]
        pattern = '|'.join(keywords)
        
        # Initialize mask
        mask = pd.Series([False] * len(self.df_main), index=self.df_main.index)
        
        # Method 1: Task name contains keywords
        name_mask = self.df_main['task_name'].str.contains(pattern, case=False, na=False)
        mask = mask | name_mask
        logger.info(f"Found {name_mask.sum()} procurement items by task_name")
        
        # Method 2: Task code patterns (SUB-, PMU-, FAB-, etc.)
        if 'task_code' in self.df_main.columns:
            code_patterns = r'(SUB-|PMU-|FAB-|MAT-|PROC-|DEL-|ORD-)'
            code_mask = self.df_main['task_code'].str.contains(code_patterns, case=False, na=False, regex=True)
            mask = mask | code_mask
            logger.info(f"Found {code_mask.sum()} procurement items by task_code pattern")
        
        result = self.df_main[mask].copy()
        logger.info(f"Total procurement/material items detected: {len(result)}")
        
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
