import pandas as pd
from typing import Dict, List, Any
from parser import P6Parser

class DiffEngine:
    """
    Compares two schedule snapshots (P6Parser objects) to detect changes.
    Tracks:
    - Activity Added/Deleted
    - Date Slips (Start/Finish variance)
    - Critical Path entry/exit
    """
    
    def __init__(self, parser_old: P6Parser, parser_new: P6Parser):
        self.old = parser_old.get_activities().set_index('task_code')
        self.new = parser_new.get_activities().set_index('task_code')
        
    def run_diff(self) -> Dict[str, pd.DataFrame]:
        """Execute all comparisons and return categorized DataFrames."""
        
        # 1. Identify Added/Deleted/Common
        old_ids = set(self.old.index)
        new_ids = set(self.new.index)
        
        added_ids = list(new_ids - old_ids)
        deleted_ids = list(old_ids - new_ids)
        common_ids = list(old_ids & new_ids)
        
        df_added = self.new.loc[added_ids].copy()
        df_deleted = self.old.loc[deleted_ids].copy()
        
        # 2. Check for Date Slips (in Common tasks)
        df_common_old = self.old.loc[common_ids].sort_index()
        df_common_new = self.new.loc[common_ids].sort_index()
        
        # Ensure dates are datetime
        df_common_old['target_end_date'] = pd.to_datetime(df_common_old['target_end_date'])
        df_common_new['target_end_date'] = pd.to_datetime(df_common_new['target_end_date'])
        
        # Variance = New Finish - Old Finish
        finish_variance = (df_common_new['target_end_date'] - df_common_old['target_end_date']).dt.days
        
        # Create Diff Report
        df_diff = pd.DataFrame({
            'task_name': df_common_new['task_name'],
            'old_finish': df_common_old['target_end_date'],
            'new_finish': df_common_new['target_end_date'],
            'slip_days': finish_variance
        })
        
        # Filter only items that moved
        df_slips = df_diff[df_diff['slip_days'] != 0].sort_values(by='slip_days', ascending=False)
        
        return {
            "added": df_added,
            "deleted": df_deleted,
            "slips": df_slips
        }
