import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import CellIsRule
from openpyxl.utils import get_column_letter
from datetime import datetime
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class DashboardGenerator:
    """
    The Artist 🎨
    Takes analyzed data and paints it into a professional Excel dashboard.
    """

    def __init__(self, analyzer, output_path: str):
        self.analyzer = analyzer
        self.output_path = output_path
        self.wb = openpyxl.Workbook()
        
        # Define Styles
        self.header_font = Font(bold=True, color="FFFFFF", size=12)
        self.header_fill = PatternFill(start_color="36454F", end_color="36454F", fill_type="solid") # Charcoal
        self.critical_font = Font(color="FF0000", bold=True)
        self.border_thin = Side(border_style="thin", color="000000")
        self.border_all = Border(left=self.border_thin, right=self.border_thin, top=self.border_thin, bottom=self.border_thin)

    def generate(self):
        """Main orchestration method to build all sheets."""
        logger.info("Generating Dashboard...")
        
        # 1. Executive Summary
        self._build_executive_summary()
        
        # 2. Stairway / Milestone Tracker
        self._build_stairway_tracker()
        
        # 3. Critical Path View
        self._build_critical_path_sheet()
        
        # 4. Procurement Log
        self._build_procurement_sheet()

        # Remove default sheet if empty
        if "Sheet" in self.wb.sheetnames and len(self.wb.sheetnames) > 1:
            del self.wb["Sheet"]

        # Save
        try:
            self.wb.save(self.output_path)
            logger.info(f"Dashboard saved to: {self.output_path}")
            return self.output_path
        except Exception as e:
            logger.error(f"Failed to save Excel: {e}")
            raise

    def _build_executive_summary(self):
        ws = self.wb.create_sheet("Executive Summary", 0)
        ws.sheet_view.showGridLines = False
        
        # Title
        ws["B2"] = "PROJECT EXECUTIVE DASHBOARD"
        ws["B2"].font = Font(size=24, bold=True, color="333333")
        
        # Get Stats
        stats = self.analyzer.get_dashboard_summary()
        
        # Metrics Grid
        metrics = [
            ("Data Date", stats.get("data_date", "N/A")),
            ("Total Activities", stats.get("total_activities", 0)),
            ("Critical Activities", stats.get("critical_activities", 0)),
            ("Slipping (>5 days)", stats.get("slipping_activities", 0)),
            ("% Critical", f"{stats.get('percent_critical', 0)}%")
        ]
        
        row = 4
        for label, value in metrics:
            ws.cell(row=row, column=2, value=label).font = Font(bold=True)
            ws.cell(row=row, column=3, value=value)
            row += 1
            
        # Add big red alert if critical path is heavy
        if stats.get("percent_critical", 0) > 20:
            ws["E4"] = "⚠️ HIGH RISK: Critical Path Saturation"
            ws["E4"].font = Font(color="FF0000", bold=True, size=14)

        self._autofit_columns(ws)

    def _build_stairway_tracker(self):
        ws = self.wb.create_sheet("Milestone Stairway")
        
        # Get Data
        df = self.analyzer.get_milestones()
        if df.empty:
            ws["A1"] = "No Milestones Found"
            return

        # Prepare Table Data
        # We want: ID, Name, Baseline Date, Current Date, Variance
        cols = ['task_code', 'task_name', 'target_end_date', 'current_finish', 'variance_days', 'status_readable']
        headers = ['ID', 'Milestone Name', 'Baseline Date', 'Forecast Date', 'Variance', 'Status']
        
        # Write Headers
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.alignment = Alignment(horizontal="center")

        # Write Data
        for r_idx, row_data in enumerate(df[cols].itertuples(index=False), 2):
            for c_idx, value in enumerate(row_data, 1):
                cell = ws.cell(row=r_idx, column=c_idx, value=value)
                cell.border = self.border_all
                
                # Format Dates
                if c_idx in [3, 4] and pd.notnull(value): # Date Columns
                    cell.number_format = 'mm/dd/yyyy'
                
                # Variance Coloring (Column 5)
                if c_idx == 5:
                    if value > 10:
                        cell.fill = PatternFill(start_color="FF9999", fill_type="solid") # Red
                    elif value > 0:
                        cell.fill = PatternFill(start_color="FFFFCC", fill_type="solid") # Yellow
                    else:
                        cell.fill = PatternFill(start_color="CCFFCC", fill_type="solid") # Green

        self._autofit_columns(ws)

    def _build_critical_path_sheet(self):
        ws = self.wb.create_sheet("Critical Path")
        df = self.analyzer.get_critical_path()
        
        if df.empty:
            ws["A1"] = "No Critical Path Activities Found"
            return

        cols = ['task_code', 'task_name', 'current_start', 'current_finish', 'total_float_hr_cnt']
        headers = ['Activity ID', 'Name', 'Start', 'Finish', 'Total Float (Hrs)']
        
        # Write Headers
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = self.header_font
            cell.fill = self.header_fill

        # Write Data
        for r_idx, row_data in enumerate(df[cols].itertuples(index=False), 2):
            for c_idx, value in enumerate(row_data, 1):
                cell = ws.cell(row=r_idx, column=c_idx, value=value)
                
                if c_idx in [3, 4] and pd.notnull(value):
                    cell.number_format = 'mm/dd/yyyy'

        self._autofit_columns(ws)

    def _build_procurement_sheet(self):
        ws = self.wb.create_sheet("Procurement Log")
        df = self.analyzer.get_procurement_log()
        
        if df.empty:
            ws["A1"] = "No Procurement Items Found (Check Keywords)"
            return
            
        cols = ['task_code', 'task_name', 'current_finish', 'status_readable']
        headers = ['ID', 'Item Description', 'Date Required', 'Status']
        
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = self.header_font
            cell.fill = PatternFill(start_color="000080", end_color="000080", fill_type="solid") # Navy
            cell.font = Font(color="FFFFFF", bold=True)

        for r_idx, row_data in enumerate(df[cols].itertuples(index=False), 2):
            for c_idx, value in enumerate(row_data, 1):
                cell = ws.cell(row=r_idx, column=c_idx, value=value)
                if c_idx == 3 and pd.notnull(value):
                    cell.number_format = 'mm/dd/yyyy'

        self._autofit_columns(ws)

    def _autofit_columns(self, ws):
        """Helper to auto-resize columns."""
        for column in ws.columns:
            max_length = 0
            column = [cell for cell in column]
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = (max_length + 2)
            ws.column_dimensions[get_column_letter(column[0].column)].width = min(adjusted_width, 50)
