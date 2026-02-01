import time
import os
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from parser import P6Parser
from analyzer import ScheduleAnalyzer
from dashboard import DashboardGenerator
from diff_engine import DiffEngine
from datetime import datetime
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class XERFileHandler(FileSystemEventHandler):
    """
    Monitors a directory for new or modified .xer files.
    Automatically processes them and generates dashboards.
    """
    
    def __init__(self, watch_dir, output_dir, config_path="monitor_config.json"):
        self.watch_dir = Path(watch_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.config_path = config_path
        self.config = self._load_config()
        
        self.last_processed = {}  # Track last processing time to avoid duplicates
        self.previous_schedules = {}  # Store previous versions for comparison
        
        logger.info(f"Monitoring directory: {self.watch_dir}")
        logger.info(f"Output directory: {self.output_dir}")
    
    def _load_config(self):
        """Load monitoring configuration"""
        default_config = {
            "auto_generate_excel": True,
            "auto_compare": True,
            "min_processing_interval": 60,  # seconds
            "notification_email": None,
            "archive_previous_versions": True
        }
        
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    return {**default_config, **json.load(f)}
            except Exception as e:
                logger.warning(f"Failed to load config: {e}. Using defaults.")
        
        return default_config
    
    def on_created(self, event):
        """Handle new file creation"""
        if not event.is_directory and event.src_path.endswith('.xer'):
            logger.info(f"New XER file detected: {event.src_path}")
            self._process_xer_file(event.src_path)
    
    def on_modified(self, event):
        """Handle file modification"""
        if not event.is_directory and event.src_path.endswith('.xer'):
            # Check if enough time has passed since last processing
            current_time = time.time()
            last_time = self.last_processed.get(event.src_path, 0)
            
            if current_time - last_time > self.config['min_processing_interval']:
                logger.info(f"XER file modified: {event.src_path}")
                self._process_xer_file(event.src_path)
            else:
                logger.debug(f"Skipping {event.src_path} - processed recently")
    
    def _process_xer_file(self, file_path):
        """Main processing logic"""
        try:
            self.last_processed[file_path] = time.time()
            
            logger.info(f"Processing: {file_path}")
            
            # Parse XER
            parser = P6Parser(file_path)
            analyzer = ScheduleAnalyzer(parser)
            
            # Generate timestamp for outputs
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = Path(file_path).stem
            
            # Generate Excel Dashboard
            if self.config['auto_generate_excel']:
                excel_path = self.output_dir / f"{base_name}_dashboard_{timestamp}.xlsx"
                logger.info(f"Generating Excel: {excel_path}")
                
                gen = DashboardGenerator(analyzer, str(excel_path))
                gen.generate()
                
                logger.info(f"✅ Excel generated: {excel_path}")
            
            # Compare with previous version
            if self.config['auto_compare'] and base_name in self.previous_schedules:
                logger.info("Running change detection...")
                
                parser_old = self.previous_schedules[base_name]['parser']
                diff = DiffEngine(parser_old, parser)
                results = diff.run_diff()
                
                # Generate change report
                report_path = self.output_dir / f"{base_name}_changes_{timestamp}.json"
                change_report = {
                    "timestamp": timestamp,
                    "file": file_path,
                    "added_count": len(results['added']),
                    "deleted_count": len(results['deleted']),
                    "slipped_count": len(results['slips'][results['slips']['slip_days'] > 0]),
                    "top_slips": results['slips'].head(10).to_dict('records') if not results['slips'].empty else []
                }
                
                with open(report_path, 'w') as f:
                    json.dump(change_report, f, indent=2, default=str)
                
                logger.info(f"✅ Change report: {report_path}")
                logger.info(f"   Added: {change_report['added_count']}, "
                          f"Deleted: {change_report['deleted_count']}, "
                          f"Slipped: {change_report['slipped_count']}")
                
                # Archive previous version if configured
                if self.config['archive_previous_versions']:
                    archive_dir = self.output_dir / "archive"
                    archive_dir.mkdir(exist_ok=True)
                    # Previous parser is already stored, no need to copy file
            
            # Store current version for future comparisons
            self.previous_schedules[base_name] = {
                'parser': parser,
                'analyzer': analyzer,
                'timestamp': timestamp
            }
            
            logger.info(f"✅ Processing complete: {file_path}")
            
        except Exception as e:
            logger.error(f"❌ Error processing {file_path}: {str(e)}", exc_info=True)
    
    def get_status_report(self):
        """Generate a status report of monitored files"""
        report = {
            "watch_directory": str(self.watch_dir),
            "output_directory": str(self.output_dir),
            "files_tracked": len(self.previous_schedules),
            "tracked_files": list(self.previous_schedules.keys()),
            "last_processed": {
                Path(k).name: datetime.fromtimestamp(v).isoformat()
                for k, v in self.last_processed.items()
            }
        }
        return report

class ScheduleMonitor:
    """
    Main monitoring service that can be run as a daemon.
    """
    
    def __init__(self, watch_dir, output_dir, config_path="monitor_config.json"):
        self.watch_dir = watch_dir
        self.output_dir = output_dir
        self.config_path = config_path
        
        self.observer = None
        self.handler = None
    
    def start(self):
        """Start the monitoring service"""
        logger.info("Starting SixTerminal Schedule Monitor...")
        
        # Create handler
        self.handler = XERFileHandler(self.watch_dir, self.output_dir, self.config_path)
        
        # Create observer
        self.observer = Observer()
        self.observer.schedule(self.handler, self.watch_dir, recursive=False)
        self.observer.start()
        
        logger.info("✅ Monitor started. Press Ctrl+C to stop.")
        
        try:
            while True:
                time.sleep(10)
                # Periodic status log
                if hasattr(self.handler, 'get_status_report'):
                    status = self.handler.get_status_report()
                    logger.debug(f"Status: Tracking {status['files_tracked']} files")
        
        except KeyboardInterrupt:
            logger.info("Stopping monitor...")
            self.stop()
    
    def stop(self):
        """Stop the monitoring service"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
        logger.info("✅ Monitor stopped.")
    
    def status(self):
        """Get current status"""
        if self.handler:
            return self.handler.get_status_report()
        return {"status": "not running"}

def create_default_config(config_path="monitor_config.json"):
    """Create a default configuration file"""
    default_config = {
        "auto_generate_excel": True,
        "auto_compare": True,
        "min_processing_interval": 60,
        "notification_email": None,
        "archive_previous_versions": True,
        "watch_directory": "./watch",
        "output_directory": "./output"
    }
    
    with open(config_path, 'w') as f:
        json.dump(default_config, f, indent=2)
    
    logger.info(f"Created default config: {config_path}")
    return config_path

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="SixTerminal Schedule Monitor")
    parser.add_argument("--watch-dir", default="./watch", help="Directory to monitor for XER files")
    parser.add_argument("--output-dir", default="./output", help="Directory for generated reports")
    parser.add_argument("--config", default="monitor_config.json", help="Configuration file path")
    parser.add_argument("--create-config", action="store_true", help="Create default config file")
    
    args = parser.parse_args()
    
    if args.create_config:
        create_default_config(args.config)
        print(f"✅ Created config file: {args.config}")
        print("Edit this file to customize monitoring behavior.")
        exit(0)
    
    # Ensure directories exist
    Path(args.watch_dir).mkdir(parents=True, exist_ok=True)
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    
    # Start monitor
    monitor = ScheduleMonitor(args.watch_dir, args.output_dir, args.config)
    monitor.start()
