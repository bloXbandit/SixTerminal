import pandas as pd
from xerparser import Xer
from typing import Dict, Any, List, Optional
import logging
import io

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class P6Parser:
    """
    Robust wrapper around xerparser (0.9.4) to extract and normalize P6 schedule data.
    Designed to feed both the Excel Dashboard engine and the AI Copilot.
    """
    
    def __init__(self, xer_path: str):
        self.xer_path = xer_path
        self.reader = None
        self.df_activities = None
        self.df_relationships = None
        self.df_wbs = None
        self.project_metadata = {}  # Store project-level data
        
        self._load_data()

    def _load_data(self):
        """Parse XER and load tables into Pandas DataFrames with type enforcement."""
        logger.info(f"Parsing XER file: {self.xer_path}")
        
        try:
            # Xer expects file content as string, not file path
            # Attempt to read with standard encoding
            try:
                with open(self.xer_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.reader = Xer(content)
            except UnicodeDecodeError:
                logger.warning("UTF-8 parsing failed. Retrying with 'cp1252' (Windows)...")
                with open(self.xer_path, 'r', encoding='cp1252', errors='replace') as f:
                    content = f.read()
                self.reader = Xer(content)

            # parsing is done by Xer init
            parser = self.reader
            
            # 1. Activities (TASK)
            # xerparser uses 'tasks' (plural) as a dictionary, not 'task'
            if hasattr(parser, 'tasks') and parser.tasks:
                # Convert dict of task objects to list of dicts for DataFrame
                tasks = []
                for task_id, task in parser.tasks.items():
                    task_dict = {
                        'task_id': task_id,
                        'task_code': getattr(task, 'task_code', ''),
                        'task_name': getattr(task, 'name', ''),
                        'status_code': getattr(task, 'status', '').name if hasattr(getattr(task, 'status', ''), 'name') else str(getattr(task, 'status', '')),
                        'target_start_date': getattr(task, 'target_start_date', None),
                        'target_end_date': getattr(task, 'target_end_date', None),
                        'act_start_date': getattr(task, 'act_start_date', None),
                        'act_end_date': getattr(task, 'act_end_date', None),
                        'early_start_date': getattr(task, 'early_start_date', None),
                        'early_end_date': getattr(task, 'early_end_date', None),
                        'late_start_date': getattr(task, 'late_start_date', None),
                        'late_end_date': getattr(task, 'late_end_date', None),
                        'total_float_hr_cnt': getattr(task, 'total_float_hr_cnt', 0),
                        'free_float_hr_cnt': getattr(task, 'free_float_hr_cnt', 0),
                        'target_drtn_hr_cnt': getattr(task, 'target_drtn_hr_cnt', 0),
                        'remain_drtn_hr_cnt': getattr(task, 'remain_drtn_hr_cnt', 0),
                        'complete_pct': getattr(task, 'phys_complete_pct', 0),
                        'task_type': getattr(task, 'task_type', '').name if hasattr(getattr(task, 'task_type', ''), 'name') else str(getattr(task, 'task_type', '')),
                        'wbs_id': getattr(task, 'wbs_id', None),
                    }
                    tasks.append(task_dict)
                
                self.df_activities = pd.DataFrame(tasks)
                logger.info(f"Loaded {len(tasks)} activities from XER")
                self._normalize_activities()
            else:
                logger.error("No tasks found in XER!")
                self.df_activities = pd.DataFrame()

            # 2. Relationships (TASKPRED)
            if hasattr(parser, 'relationships') and parser.relationships:
                preds = []
                for rel_id, rel in parser.relationships.items():
                    pred_dict = {
                        'pred_id': rel_id,
                        'pred_task_id': getattr(rel, 'predecessor_task_id', None),
                        'task_id': getattr(rel, 'task_id', None),
                        'pred_type': getattr(rel, 'pred_type', '').name if hasattr(getattr(rel, 'pred_type', ''), 'name') else str(getattr(rel, 'pred_type', '')),
                        'lag_hr_cnt': getattr(rel, 'lag_hr_cnt', 0),
                    }
                    preds.append(pred_dict)
                self.df_relationships = pd.DataFrame(preds)
            else:
                self.df_relationships = pd.DataFrame()
            
            # 3. WBS (PROJWBS)
            if hasattr(parser, 'wbs_nodes') and parser.wbs_nodes:
                wbs = []
                for wbs_id, wbs_node in parser.wbs_nodes.items():
                    wbs_dict = {
                        'wbs_id': wbs_id,
                        'wbs_name': getattr(wbs_node, 'name', ''),
                        'wbs_short_name': getattr(wbs_node, 'wbs_short_name', ''),
                        'parent_wbs_id': getattr(wbs_node, 'parent_wbs_id', None),
                    }
                    wbs.append(wbs_dict)
                self.df_wbs = pd.DataFrame(wbs)
            else:
                self.df_wbs = pd.DataFrame()
            
            # Extract project-level metadata
            if hasattr(parser, 'projects') and parser.projects:
                proj = list(parser.projects.values())[0]
                self.project_metadata = {
                    'project_name': getattr(proj, 'name', 'Unknown'),
                    'data_date': getattr(proj, 'data_date', None),
                    'plan_start_date': getattr(proj, 'plan_start_date', None),
                    'must_fin_by_date': getattr(proj, 'must_fin_by_date', None),
                    'last_recalc_date': getattr(proj, 'last_recalc_date', None),
                }
                logger.info(f"Project: {self.project_metadata['project_name']}")
                logger.info(f"Data Date: {self.project_metadata['data_date']}")
                
            logger.info("XER Parsing Complete. Data loaded into memory.")
            
        except Exception as e:
            logger.error(f"Failed to parse XER: {str(e)}")
            # Fallback for Streamlit to not crash completely
            self.df_activities = pd.DataFrame()
            raise e

    def _normalize_activities(self):
        """Clean up date formats and handle nulls."""
        if self.df_activities.empty: return

        date_cols = ['target_start_date', 'target_end_date', 'act_start_date', 'act_end_date', 'early_start_date', 'early_end_date']
        
        for col in date_cols:
            if col in self.df_activities.columns:
                self.df_activities[col] = pd.to_datetime(self.df_activities[col], errors='coerce')

    def get_activities(self) -> pd.DataFrame:
        """Return the raw activities dataframe."""
        return self.df_activities

    def get_llm_context(self, summary_only=True) -> Dict[str, Any]:
        """
        Generates a token-efficient summary for the AI Copilot.
        """
        if self.df_activities is None or self.df_activities.empty:
            return {"error": "No data loaded"}
            
        total_tasks = len(self.df_activities)
        # Check column names carefully as xerparser might lowercase them
        status_col = 'status_code' if 'status_code' in self.df_activities.columns else 'status_code'
        
        completed = len(self.df_activities[self.df_activities[status_col] == 'TK_Complete']) if status_col in self.df_activities else 0
        in_progress = len(self.df_activities[self.df_activities[status_col] == 'TK_Active']) if status_col in self.df_activities else 0
        
        context = {
            "project_metrics": {
                "total_activities": total_tasks,
                "completed": completed,
                "in_progress": in_progress,
                "project_data_date": str(datetime.now().date()) # Placeholder
            }
        }
        return context

if __name__ == "__main__":
    import sys
    from datetime import datetime
    if len(sys.argv) > 1:
        parser = P6Parser(sys.argv[1])
        print(parser.get_activities().head())
