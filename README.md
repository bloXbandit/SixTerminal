# SixTerminal 🏗️

**The Modern Interface for Primavera P6**

A powerful Python application for analyzing, visualizing, and tracking Primavera P6 schedules with AI-powered insights.

![Version](https://img.shields.io/badge/version-2.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

---

## Features

### 📊 **Stairway Visualization**
Track milestone progression with visual baseline vs forecast comparison. The signature "stairway chart" makes schedule health immediately clear to stakeholders.

### 🧠 **AI Copilot**
Ask natural language questions about your schedule:
- "What are the top 3 schedule risks?"
- "Why is the project delayed?"
- "Which milestones are at risk?"

Powered by OpenAI GPT-4 with context-aware responses based on your live schedule data.

### ⚡ **Auto-Analysis**
- Instant critical path identification
- Variance analysis (baseline vs current)
- Schedule health indicators
- Procurement log extraction

### 🔍 **Change Detection**
Compare two schedule versions to track:
- Added/deleted activities
- Date slips and improvements
- Visual slip analysis
- Automated change reports

### 📑 **Excel Dashboards**
Generate stakeholder-ready reports with:
- Professional formatting and conditional colors
- Embedded stairway charts
- Multiple analysis sheets
- Executive summary with KPIs

### 🔄 **File Monitoring** (Automation)
Automatically process new XER files:
- Watch a directory for schedule updates
- Auto-generate dashboards
- Compare with previous versions
- Generate change reports

---

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/bloXbandit/SixTerminal.git
cd SixTerminal

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Usage

#### Option 1: Web Interface (Recommended)

```bash
streamlit run src/app.py
```

Then open your browser to `http://localhost:8501`

#### Option 2: Command Line

```python
from src.parser import P6Parser
from src.analyzer import ScheduleAnalyzer
from src.dashboard import DashboardGenerator

# Parse XER file
parser = P6Parser('your_schedule.xer')
analyzer = ScheduleAnalyzer(parser)

# Generate Excel dashboard
gen = DashboardGenerator(analyzer, 'output_dashboard.xlsx')
gen.generate()
```

#### Option 3: File Monitoring (Automation)

```bash
# Create default config
python src/monitor.py --create-config

# Start monitoring
python src/monitor.py --watch-dir ./watch --output-dir ./output
```

Place XER files in the `./watch` directory and dashboards will be auto-generated in `./output`.

---

## Configuration

### AI Copilot Setup

1. Get an OpenAI API key from https://platform.openai.com/api-keys
2. Configure in the web interface:
   - Go to **Settings** in the sidebar
   - Enter your API key
   - Select your preferred model (GPT-4 Turbo recommended)
   - Click **Save Settings**

Alternatively, set environment variable:
```bash
export OPENAI_API_KEY="your-api-key-here"
```

### Analysis Thresholds

Customize in `config.json`:

```json
{
  "ai_provider": "openai",
  "ai_model": "gpt-4-turbo",
  "api_key": "your-key-here",
  "analysis": {
    "critical_float_threshold": 0,
    "slippage_threshold_days": 5
  }
}
```

---

## Requirements

- **Python**: 3.11+
- **P6 Version**: Compatible with all P6 XER exports (Professional & EPPM)
- **Operating System**: Windows, macOS, Linux

### Dependencies

```
xerparser==0.9.4
pandas==2.3.3
openpyxl==3.1.5
streamlit==1.53.1
plotly==6.5.2
openai>=1.0.0
watchdog==6.0.0
```

---

## Project Structure

```
SixTerminal/
├── src/
│   ├── parser.py          # XER file parsing with encoding handling
│   ├── analyzer.py        # Schedule analysis engine
│   ├── dashboard.py       # Excel generation with charts
│   ├── copilot.py         # AI integration
│   ├── diff_engine.py     # Change detection
│   ├── monitor.py         # File monitoring automation
│   ├── config.py          # Configuration management
│   └── app.py             # Streamlit web interface
├── docs/
│   ├── P6_Stairway_Tracker_Planning_Document.md
│   ├── AI_Copilot_Integration.md
│   ├── Live_P6_Integration_and_Change_Tracking.md
│   ├── CODE_REVIEW_PHASE_1.md
│   └── UPDATE_ANALYSIS_JAN31.md
├── tests/                 # Unit tests (coming soon)
├── examples/              # Example XER files and outputs
├── requirements.txt
└── README.md
```

---

## Features in Detail

### Dashboard Tabs

**🚀 Executive Summary**
- Project health KPIs
- Critical path timeline
- Schedule health indicators
- Risk alerts

**📈 Stairway Visuals**
- Interactive milestone chart
- Baseline vs forecast comparison
- Variance analysis table
- Color-coded status

**🔍 Compare Schedules**
- Upload previous version
- Detect added/deleted activities
- Visualize date slips
- Export change reports

**📋 Data Tables**
- Full schedule view
- Search and filter
- Column customization
- CSV export

**🤖 AI Copilot**
- Natural language queries
- Context-aware responses
- Suggested questions
- Chat history

### Excel Dashboard Sheets

1. **Executive Summary** - High-level metrics and alerts
2. **Milestone Stairway** - Visual chart + data table
3. **Critical Path** - Top critical activities
4. **Procurement Log** - Material and submittal tracking

---

## Performance

- **Parsing Speed**: <5 seconds for 1000-activity schedules
- **Dashboard Generation**: <10 seconds
- **AI Response Time**: 2-5 seconds (depends on OpenAI API)
- **Memory Usage**: ~200MB for typical schedules

### Optimization Tips

- Use the built-in caching for repeated analyses
- Filter data in Data Tables view for large schedules
- Clear cache in Settings if memory issues occur

---

## Troubleshooting

### XER File Won't Parse

**Issue**: `ValueError: invalid XER file`

**Solution**:
- Ensure file is a valid P6 export (not corrupted)
- Try re-exporting from P6
- Check file encoding (tool handles UTF-8 and Windows cp1252)

### AI Copilot Not Responding

**Issue**: API key errors or timeouts

**Solution**:
- Verify API key is correct in Settings
- Check OpenAI account has credits
- Try switching to a different model (GPT-3.5 Turbo is faster/cheaper)
- Check internet connectivity

### Slow Performance

**Issue**: Large schedules take too long

**Solution**:
- Use "Clear Cache" in Settings
- Filter activities in Data Tables view
- Consider upgrading hardware for 5000+ activity schedules

---

## Development

### Running Tests

```bash
pytest tests/
```

### Code Style

```bash
# Format code
black src/

# Lint
pylint src/
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## Roadmap

### Phase 3 (In Progress - 70%)
- ✅ File monitoring automation
- ✅ Enhanced UI with settings page
- ✅ AI error handling with retries
- ✅ Compare schedules UI
- ⏳ Unit test framework
- ⏳ Multi-project dashboard

### Future Enhancements
- S-curve analytics
- Burn-down charts
- PDF export option
- Direct P6 database connection
- Mobile app (React Native)
- Real-time collaboration features

---

## Architecture

### Data Flow

```
XER File → Parser → Analyzer → Dashboard Generator → Excel Output
                ↓
            AI Copilot (with context)
                ↓
            Change Detection (Diff Engine)
```

### Key Design Principles

- **Modularity**: Each component is independent and testable
- **Performance**: Caching and lazy loading for large datasets
- **Robustness**: Encoding fallback and error handling
- **Extensibility**: Easy to add new analysis modules

---

## Credits

**Developer**: Ecarg (OpenClaw)  
**Planning & Review**: Manus AI  
**Project**: SixTerminal

### Built With

- [xerparser](https://github.com/bramburn/xerparser) - XER file parsing
- [Streamlit](https://streamlit.io/) - Web interface
- [Plotly](https://plotly.com/) - Interactive charts
- [OpenPyXL](https://openpyxl.readthedocs.io/) - Excel generation
- [OpenAI](https://openai.com/) - AI Copilot

---

## License

MIT License - see [LICENSE](LICENSE) file for details

---

## Support

- **Issues**: https://github.com/bloXbandit/SixTerminal/issues
- **Discussions**: https://github.com/bloXbandit/SixTerminal/discussions
- **Documentation**: [Wiki](https://github.com/bloXbandit/SixTerminal/wiki)

---

## Changelog

### v2.0 (January 2026) - Production Release
- ✅ Complete UI overhaul with enhanced Streamlit interface
- ✅ AI Copilot with OpenAI integration
- ✅ Excel stairway chart visualization
- ✅ Change detection engine
- ✅ File monitoring automation
- ✅ Configuration management system
- ✅ Performance optimizations with caching
- ✅ Settings page with API key management
- ✅ Comprehensive help documentation
- ✅ Compare schedules UI with visual slip analysis
- ✅ AI error handling with retry logic

### v1.0 (January 2026) - Initial Release
- XER parsing and analysis
- Basic Excel dashboard generation
- Critical path identification
- Milestone tracking

---

**Made with ❤️ for Project Schedulers**
