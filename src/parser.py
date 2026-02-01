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
            if hasattr(parser, 'task'):
                # Convert list of objects to dicts for DataFrame
                tasks = [vars(t) for t in parser.task] if parser.task else []
                self.df_activities = pd.DataFrame(tasks)
                self._normalize_activities()
            else:
                logger.error("No TASK table found in XER!")
                self.df_activities = pd.DataFrame()

            # 2. Relationships (TASKPRED)
            if hasattr(parser, 'taskpred'):
                preds = [vars(p) for p in parser.taskpred] if parser.taskpred else []
                self.df_relationships = pd.DataFrame(preds)
            
            # 3. WBS (PROJWBS)
            if hasattr(parser, 'projwbs'):
                wbs = [vars(w) for w in parser.projwbs] if parser.projwbs else []
                self.df_wbs = pd.DataFrame(wbs)
                
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
