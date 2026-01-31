import pandas as pd
from xerparser.reader import Reader
from typing import Dict, Any, List, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class P6Parser:
    """
    Robust wrapper around PyP6XER to extract and normalize P6 schedule data.
    Designed to feed both the Excel Dashboard engine and the AI Copilot.
    """
    
    def __init__(self, xer_path: str):
        self.xer_path = xer_path
        self.reader = Reader(xer_path)
        self.tables = {}
        self.project_data = {}
        
        # Core dataframes
        self.df_activities = None
        self.df_relationships = None
        self.df_wbs = None
        self.df_codes = None
        
        # Load immediately
        self._load_data()

    def _load_data(self):
        """Parse XER and load tables into Pandas DataFrames with type enforcement."""
        logger.info(f"Parsing XER file: {self.xer_path}")
        
        try:
            # parsing is done by Reader init, just accessing parser items
            parser = self.reader.parser
            
            # 1. Activities (TASK)
            # We map P6 internal names to human friendly names for our downstream apps
            if hasattr(parser, 'task'):
                self.df_activities = pd.DataFrame(parser.task)
                self._normalize_activities()
            else:
                logger.error("No TASK table found in XER!")

            # 2. Relationships (TASKPRED)
            if hasattr(parser, 'taskpred'):
                self.df_relationships = pd.DataFrame(parser.taskpred)
            
            # 3. WBS (PROJWBS) - Essential for hierarchy
            if hasattr(parser, 'projwbs'):
                self.df_wbs = pd.DataFrame(parser.projwbs)
                
            # 4. Activity Codes (ACTVCODE + ACTVTYPE) - Essential for filtering
            # Note: This usually requires joining ACTVCODE assignment with ACTVTYPE definitions
            # Implementing robust join logic later in analyzer
            
            logger.info("XER Parsing Complete. Data loaded into memory.")
            
        except Exception as e:
            logger.error(f"Failed to parse XER: {str(e)}")
            raise e

    def _normalize_activities(self):
        """Clean up date formats and handle nulls."""
        date_cols = ['target_start_date', 'target_end_date', 'act_start_date', 'act_end_date', 'early_start_date', 'early_end_date']
        
        for col in date_cols:
            if col in self.df_activities.columns:
                self.df_activities[col] = pd.to_datetime(self.df_activities[col], errors='coerce')

    def get_activities(self) -> pd.DataFrame:
        """Return the raw activities dataframe."""
        return self.df_activities

    def get_relationships(self) -> pd.DataFrame:
        """Return the relationships dataframe."""
        return self.df_relationships

    def get_llm_context(self, summary_only=True) -> Dict[str, Any]:
        """
        Generates a token-efficient summary for the AI Copilot.
        The AI doesn't need every row, it needs the 'Health Stats'.
        """
        if self.df_activities is None:
            return {"error": "No data loaded"}
            
        total_tasks = len(self.df_activities)
        completed = len(self.df_activities[self.df_activities['status_code'] == 'TK_Complete'])
        in_progress = len(self.df_activities[self.df_activities['status_code'] == 'TK_Active'])
        not_started = total_tasks - completed - in_progress
        
        # Calculate simplistic start/finish bounds
        start_date = self.df_activities['target_start_date'].min()
        finish_date = self.df_activities['target_end_date'].max()
        
        context = {
            "project_metrics": {
                "total_activities": total_tasks,
                "completed": completed,
                "in_progress": in_progress,
                "not_started": not_started,
                "project_start": str(start_date),
                "project_finish": str(finish_date)
            },
            # We will populate 'critical_path_count' and 'high_variance_count' 
            # once the Analyzer module is built.
            "analysis_ready": False 
        }
        return context

if __name__ == "__main__":
    # Test block
    import sys
    if len(sys.argv) > 1:
        parser = P6Parser(sys.argv[1])
        print(parser.get_llm_context())
