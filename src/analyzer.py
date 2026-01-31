import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional
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
        
        # 1. Map P6 Status Codes to Human Readable
        status_map = {
            'TK_NotStart': 'Not Started',
            'TK_Active': 'In Progress',
            'TK_Complete': 'Completed'
        }
        raw_tasks['status_readable'] = raw_tasks['status_code'].map(status_map).fillna('Unknown')

        # 2. Define "Current Start" and "Current Finish" based on Status
        # P6 Logic:
        # - If Completed: Use Actual Start / Actual Finish
        # - If In Progress: Use Actual Start / Early Finish (Forecast)
        # - If Not Started: Use Early Start / Early Finish
        
        raw_tasks['current_start'] = np.where(
            raw_tasks['status_code'] == 'TK_NotStart', 
            raw_tasks['early_start_date'], 
            raw_tasks['act_start_date']
        )
        
        raw_tasks['current_finish'] = np.where(
            raw_tasks['status_code'] == 'TK_Complete', 
            raw_tasks['act_end_date'], 
            raw_tasks['early_end_date']
        )

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
        if self.df_main is None: return pd.DataFrame()
        
        crit = self.df_main[self.df_main['is_critical']].copy()
        return crit.sort_values(by='current_start')

    def get_milestones(self) -> pd.DataFrame:
        """
        Extracts Start Milestones and Finish Milestones.
        P6 'task_type': 
        - TT_MileStart (Start Milestone)
        - TT_Mile (Finish Milestone)
        """
        if self.df_main is None: return pd.DataFrame()
        
        mask = self.df_main['task_type'].isin(['TT_Mile', 'TT_MileStart'])
        milestones = self.df_main[mask].copy()
        return milestones.sort_values(by='current_finish')

    def get_procurement_log(self) -> pd.DataFrame:
        """
        Filters activities related to Procurement/Submittals.
        Logic: Looks for 'Submittal', 'Procurement', 'Order', 'Deliver' in name,
        OR checks WBS hierarchy (if mapped).
        """
        if self.df_main is None: return pd.DataFrame()
        
        # Simple keyword filter for Phase 1. 
        # Phase 2: Use Activity Codes or WBS.
        keywords = ['submittal', 'procure', 'fabricat', 'deliver', 'approval']
        pattern = '|'.join(keywords)
        
        # Case insensitive regex search
        mask = self.df_main['task_name'].str.contains(pattern, case=False, na=False)
        return self.df_main[mask].sort_values(by='current_finish')

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """
        Returns high-level metrics for the Executive Dashboard sheet.
        """
        if self.df_main is None: return {}
        
        total = len(self.df_main)
        critical_count = len(self.df_main[self.df_main['is_critical']])
        
        # "Slipping" defined as Variance > 5 days (customizable)
        slipping_count = len(self.df_main[self.df_main['variance_days'] > 5])
        
        return {
            "data_date": self.analysis_date.strftime('%Y-%m-%d'),
            "total_activities": total,
            "critical_activities": critical_count,
            "slipping_activities": slipping_count,
            "percent_critical": round((critical_count / total) * 100, 1) if total > 0 else 0
        }
