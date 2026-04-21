import pandas as pd
from typing import Dict, Any, List, Optional
import logging
import io
from datetime import datetime

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
        self._llm_context_cache = None  # Cache for expensive context building
        self._cp_chain = None  # Critical path chain built at load time
        
        self._load_data()

    def _load_data(self):
        """Parse XER and load tables into Pandas DataFrames with type enforcement."""
        try:
            from xerparser import Xer
        except ImportError:
            raise ImportError(
                "xerparser is not installed. Run: pip install xerparser"
            )
        logger.info(f"Parsing XER file: {self.xer_path}")
        
        try:
            self.reader = Xer.reader(self.xer_path)

            # parsing is done by Xer init
            parser = self.reader
            
            # Debug: Log all available attributes on the parser object
            available_attrs = [attr for attr in dir(parser) if not attr.startswith('_')]
            logger.info(f"Parser attributes: {available_attrs}")
            
            # 1. Activities (TASK)
            # Check for both 'tasks' (dict) and 'task' (list) to be robust
            if hasattr(parser, 'tasks') and parser.tasks:
                logger.info(f"Found 'tasks' dictionary with {len(parser.tasks)} items")
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
                        # Constraint fields
                        'cstr_type': getattr(task, 'cstr_type', None),
                        'cstr_date': getattr(task, 'cstr_date', None),
                        'cstr_type2': getattr(task, 'cstr_type2', None),
                        'cstr_date2': getattr(task, 'cstr_date2', None),
                        # Float path fields (P6 native path grouping)
                        'float_path': getattr(task, 'float_path', None),
                        'float_path_order': getattr(task, 'float_path_order', None),
                        'is_longest_path': getattr(task, 'is_longest_path', None),
                    }
                    tasks.append(task_dict)
                
                self.df_activities = pd.DataFrame(tasks)
                logger.info(f"Loaded {len(tasks)} activities from XER (via tasks dict)")
                self._normalize_activities()
            
            elif hasattr(parser, 'task') and parser.task:
                logger.info(f"Found 'task' list with {len(parser.task)} items")
                # Fallback for list-based parser
                tasks = [vars(t) for t in parser.task]
                self.df_activities = pd.DataFrame(tasks)
                logger.info(f"Loaded {len(tasks)} activities from XER (via task list)")
                self._normalize_activities()
                
            else:
                logger.error("No tasks found in XER! Checked 'tasks' and 'task'.")
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
            self._build_cp_chain()
            
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

    def _build_cp_chain(self):
        """Build critical path chain from zero-float activities and relationship network."""
        # Fix import path for Render environment
        import sys, os
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        try:
            from critical_path import build_critical_chain
            if self.df_activities is None or self.df_activities.empty:
                return

            # Normalize tasks to standard dict format
            tasks = []
            for _, row in self.df_activities.iterrows():
                tasks.append(self._normalize_task_row(row))

            # Normalize relationships to standard format
            rels = []
            if self.df_relationships is not None and not self.df_relationships.empty:
                for _, row in self.df_relationships.iterrows():
                    rels.append({
                        "task_id": str(row.get("task_id", "")),
                        "pred_task_id": str(row.get("pred_task_id", "")),
                    })

            critical_ids = {t["id"] for t in tasks if t["critical"]}
            self._cp_chain = build_critical_chain(
                tasks=tasks,
                relationships=rels,
                target_name=None,
                critical_ids=critical_ids,
            )
        except Exception as e:
            logger.warning(f"XER CP chain build failed: {e}")
            self._cp_chain = None

    def _normalize_task_row(self, row) -> Dict:
        """Normalize a df_activities row to a standard task dict for CP engine."""
        task_type_raw = str(row.get("task_type", "") or "").strip()
        task_type_lo = task_type_raw.lower()
        is_milestone = task_type_lo in ("tt_mile", "milestone", "tt_finishmile")
        is_summary   = task_type_lo in ("tt_wbs", "wbs_summary", "tt_rsrc")
        # total_float_hr_cnt is standard; fall back to remain_float_hr_cnt which
        # some XER exports use instead (especially older P6 versions)
        raw_float = row.get("total_float_hr_cnt") or row.get("remain_float_hr_cnt") or row.get("free_float_hr_cnt")
        try:
            float_hrs = float(raw_float) if raw_float is not None else 8.0  # default 1 day if truly missing
        except (ValueError, TypeError):
            float_hrs = 8.0
        # Constraint type: normalize enum/string to readable label
        def _cstr_label(raw):
            if raw is None: return None
            s = str(raw).strip()
            if not s or s.lower() in ('none', 'cs_alap', 'tt_alap'): return None
            _map = {
                'CS_MANDFIN': 'Mandatory Finish', 'CS_MANDSTART': 'Mandatory Start',
                'CS_MEOFIN': 'Finish On', 'CS_MEOSTART': 'Start On',
                'CS_MSOEFIN': 'Finish On or Before', 'CS_MSOESTART': 'Start On or Before',
                'CS_MSOIFIN': 'Finish On or After', 'CS_MSOISTART': 'Start On or After',
                'CS_ASAP': None, 'CS_ALAP': None,
            }
            upper = s.upper()
            return _map.get(upper, s)  # return raw string if not in map

        def _cstr_date_str(raw):
            if raw is None: return None
            try: return str(raw)[:10]
            except Exception: return None

        cstr_label  = _cstr_label(row.get('cstr_type'))
        cstr_date   = _cstr_date_str(row.get('cstr_date'))
        cstr_label2 = _cstr_label(row.get('cstr_type2'))
        cstr_date2  = _cstr_date_str(row.get('cstr_date2'))

        # Float path fields
        try: float_path = int(row.get('float_path') or 0)
        except (TypeError, ValueError): float_path = 0
        try: float_path_order = int(row.get('float_path_order') or 0)
        except (TypeError, ValueError): float_path_order = 0
        is_longest = bool(row.get('is_longest_path'))

        return {
            "id": str(row.get("task_id", "")),
            "task_code": str(row.get("task_code", "") or ""),  # P6 activity code (e.g. PS-CMIL-1170)
            "name": str(row.get("task_name", "") or ""),
            "milestone": is_milestone,
            "summary": is_summary,
            "percent_complete": float(row.get("complete_pct", 0) or 0),
            "critical": float_hrs <= 0,
            "near_critical": 0 < float_hrs <= 80,  # 80h = 10 working days
            "total_float_hrs": float_hrs,
            "finish": str(row.get("early_end_date") or row.get("target_end_date") or "")[:10],
            "start": str(row.get("early_start_date") or row.get("target_start_date") or "")[:10],
            # Constraint fields
            "cstr_type": cstr_label,
            "cstr_date": cstr_date,
            "cstr_type2": cstr_label2,
            "cstr_date2": cstr_date2,
            # Float path fields
            "float_path": float_path,
            "float_path_order": float_path_order,
            "is_longest_path": is_longest,
        }

    def get_critical_chain(self, target_name: Optional[str] = None) -> Dict:
        """Build and return CP chain for any target activity (or full project CP)."""
        # Fix import path for Render environment
        import sys, os
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        try:
            from critical_path import build_critical_chain
            if self.df_activities is None or self.df_activities.empty:
                return {"error": "No activities loaded"}

            tasks = [self._normalize_task_row(row) for _, row in self.df_activities.iterrows()]

            rels = []
            if self.df_relationships is not None and not self.df_relationships.empty:
                for _, row in self.df_relationships.iterrows():
                    rels.append({
                        "task_id": str(row.get("task_id", "")),
                        "pred_task_id": str(row.get("pred_task_id", "")),
                    })
            critical_ids = {t["id"] for t in tasks if t["critical"]}
            return build_critical_chain(
                tasks=tasks,
                relationships=rels,
                target_name=target_name,
                critical_ids=critical_ids,
            )
        except Exception as e:
            return {"error": str(e)}

    def get_activities(self) -> pd.DataFrame:
        """Return the raw activities dataframe."""
        return self.df_activities

    def get_llm_context(self, summary_only=True, force_refresh=False) -> Dict[str, Any]:
        """
        Generates a rich, token-efficient summary for the AI Copilot to construct narratives.
        Cached to avoid recalculation on every query.
        """
        # Return cached context if available and not forcing refresh
        if self._llm_context_cache is not None and not force_refresh:
            return self._llm_context_cache
            
        if self.df_activities is None or self.df_activities.empty:
            return {"error": "No data loaded"}
            
        total_tasks = len(self.df_activities)
        # Check column names carefully as xerparser might lowercase them
        status_col = 'status_code' if 'status_code' in self.df_activities.columns else 'status_code'
        
        # Calculate status counts
        if status_col in self.df_activities.columns:
            completed = len(self.df_activities[self.df_activities[status_col] == 'TK_Complete'])
            in_progress = len(self.df_activities[self.df_activities[status_col] == 'TK_Active'])
            not_started = len(self.df_activities[self.df_activities[status_col] == 'TK_NotStart'])
        else:
            completed = 0
            in_progress = 0
            not_started = 0
            
        # Extract WBS High-Level Structure (Level 1/2 ONLY - Token Optimized!)
        wbs_summary = []
        if self.df_wbs is not None and not self.df_wbs.empty:
            # Get top level nodes (no parent)
            top_nodes = self.df_wbs[self.df_wbs['parent_wbs_id'].isnull()].head(10)
            if top_nodes.empty:
                # Fallback: take first 5 nodes
                top_nodes = self.df_wbs.head(5)
            
            for _, node in top_nodes.iterrows():
                wbs_summary.append(node.get('wbs_name', 'Unknown Phase'))
        
        # Get data_date early for use in DCMA calculations
        data_date = self.project_metadata.get('data_date')
        
        # DCMA 14-Point Metrics (Key Indicators)
        dcma_metrics = {}
        
        # Metric #5: Hard Constraints
        if 'cstr_type' in self.df_activities.columns:
            constrained = self.df_activities['cstr_type'].notna().sum()
            dcma_metrics['constraints_count'] = constrained
            dcma_metrics['constraints_percent'] = f"{(constrained / total_tasks * 100):.2f}%"
        
        # Metric #7: Negative Float
        if 'total_float_hr_cnt' in self.df_activities.columns:
            neg_float = (self.df_activities['total_float_hr_cnt'] < 0).sum()
            dcma_metrics['negative_float_count'] = neg_float
        
        # Metric #11: Missed Tasks (started but 0% complete)
        if data_date and 'act_start_date' in self.df_activities.columns and 'complete_pct' in self.df_activities.columns:
            missed = ((self.df_activities['act_start_date'].notna()) & 
                      (self.df_activities['act_start_date'] < data_date) & 
                      (self.df_activities['complete_pct'] == 0)).sum()
            dcma_metrics['missed_tasks_count'] = missed
        
        # Logic Health
        if self.df_relationships is not None and not self.df_relationships.empty:
            has_pred = self.df_activities['task_id'].isin(self.df_relationships['task_id'])
            has_succ = self.df_activities['task_id'].isin(self.df_relationships['pred_task_id'])
            fully_linked = (has_pred & has_succ).sum()
            dcma_metrics['logic_percent'] = f"{(fully_linked / total_tasks * 100):.1f}%"
        
        # Format dates for narrative
        data_date = self.project_metadata.get('data_date')
        if data_date:
            data_date_str = data_date.strftime('%B %d, %Y')
        else:
            data_date_str = "Unknown"

        critical_count = int(
            len(self.df_activities[self.df_activities['total_float_hr_cnt'] <= 0])
            if 'total_float_hr_cnt' in self.df_activities.columns else 0
        )

        # Near-critical: 0 < float <= 80h (10 working days), not WBS summary
        near_critical_list = []
        if 'total_float_hr_cnt' in self.df_activities.columns:
            nc_df = self.df_activities[
                (self.df_activities['total_float_hr_cnt'] > 0) &
                (self.df_activities['total_float_hr_cnt'] <= 80)
            ].copy()
            # Filter out WBS summaries
            if 'task_type' in nc_df.columns:
                nc_df = nc_df[~nc_df['task_type'].str.lower().isin(['tt_wbs', 'wbs_summary', 'tt_rsrc'])]
            nc_df = nc_df.sort_values('total_float_hr_cnt')
            for _, r in nc_df.head(15).iterrows():
                float_days = round(float(r['total_float_hr_cnt']) / 8.0, 1)
                finish = str(r.get('early_end_date') or r.get('target_end_date') or '')[:10]
                near_critical_list.append(
                    f"  - {r.get('task_name', 'Unknown')} | Float: {float_days} cal days | Finish: {finish}"
                )

        # Build CP chain context block
        cp_context = ""
        if self._cp_chain and not self._cp_chain.get("error"):
            try:
                # Fix import path for Render environment
                import sys, os
                here = os.path.dirname(os.path.abspath(__file__))
                if here not in sys.path:
                    sys.path.insert(0, here)
                from critical_path import format_chain_for_context
                cp_context = format_chain_for_context(self._cp_chain)
            except Exception:
                pass

        context = {
            "project_info": {
                "name": self.project_metadata.get('project_name', 'Unnamed Project'),
                "data_date": data_date_str,
                "plan_start": self.project_metadata.get('plan_start_date', 'N/A'),
                "must_finish": self.project_metadata.get('must_fin_by_date', 'N/A')
            },
            "project_metrics": {
                "total_activities": total_tasks,
                "completed": completed,
                "in_progress": in_progress,
                "not_started": not_started,
                "percent_complete": f"{(completed / total_tasks * 100):.1f}%" if total_tasks > 0 else "0%"
            },
            "wbs_phases": wbs_summary,
            "critical_stats": {
                "critical_count": critical_count
            },
            "dcma_metrics": dcma_metrics,
            "cp_chain_context": cp_context,
            "near_critical_context": (
                f"NEAR-CRITICAL ACTIVITIES (0 < float \u2264 10 days, showing top {len(near_critical_list)}):\n"
                + "\n".join(near_critical_list)
            ) if near_critical_list else "",
        }
        
        # Cache the context for future queries
        self._llm_context_cache = context
        return context

if __name__ == "__main__":
    import sys
    from datetime import datetime

    if "--build-milestones" in sys.argv:
        import os, json
        try:
            import openpyxl
        except ImportError:
            import subprocess
            subprocess.check_call(["pip", "install", "openpyxl", "--quiet"])
            import openpyxl

        BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        XLSX = os.path.join(BASE, "Milestone Map.xlsx")
        PROJ_DIR = os.path.join(BASE, "copilot_web", "projects")

        SLUG_MAP = {
            "Anaheim, CA": "anaheim_ca", "Anna, TX": "anna_tx",
            "Aventura, FL": "aventura_fl", "Colorado Springs, CO": "colorado_springs_co",
            "Davenport, FL": "davenport_fl", "Delray, FL": "delray_fl",
            "Fairfax, VA": "fairfax_va", "Frisco, TX": "frisco_tx",
            "Meridian, ID": "meridian_id", "Mesa, AZ": "mesa_az",
            "Mt Juliet, TN": "mt_juliet_tn", "San Diego, CA": "san_diego_ca",
            "Selma, NC": "selma_nc", "Willis, TX": "willis_tx",
        }

        def _na(v):
            return v is None or str(v).strip().upper() == "N/A"

        print(f"Reading: {XLSX}")
        wb = openpyxl.load_workbook(XLSX, read_only=True)
        ws = wb.active
        by_project = {}

        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                continue
            ptype  = str(row[0]).strip() if row[0] else ""
            pname  = str(row[1]).strip() if row[1] else ""
            std    = str(row[2]).strip() if row[2] else ""
            aid    = row[3]
            srt    = row[4]
            aname  = str(row[5]).strip() if row[5] else ""
            if not pname or not std:
                continue
            if _na(aid) and _na(aname):
                continue
            if pname not in by_project:
                by_project[pname] = {"type": ptype, "milestones": []}
            by_project[pname]["milestones"].append({
                "standardized_name": std,
                "activity_id": None if _na(aid) else aid,
                "activity_name": None if _na(aname) else aname,
                "sort": srt,
            })

        written = 0
        for pname, data in by_project.items():
            slug = SLUG_MAP.get(pname)
            if not slug:
                print(f"  SKIPPED (no bucket): {pname}")
                continue
            out = os.path.join(PROJ_DIR, slug, "milestone_map.json")
            payload = {
                "project": pname,
                "type": data["type"],
                "milestones": sorted(data["milestones"], key=lambda x: x["sort"] or 99)
            }
            with open(out, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            print(f"  OK  {slug}: {len(data['milestones'])} milestones")
            written += 1

        print(f"\nDone. {written} milestone_map.json files written.")

    elif len(sys.argv) > 1:
        parser = P6Parser(sys.argv[1])
        print(parser.get_activities().head())
