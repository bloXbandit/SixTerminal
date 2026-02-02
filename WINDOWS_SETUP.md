# SixTerminal - Windows Portable Setup Guide

## 📦 What You're Getting

A portable Windows application that runs SixTerminal on any Windows machine without complex installation.

---

## 🚀 Quick Start (3 Steps)

### Step 1: Get the Files
**Option A - From GitHub:**
1. Download the repository as ZIP: https://github.com/bloXbandit/SixTerminal
2. Extract to a folder (e.g., `C:\SixTerminal`)

**Option B - Copy the Folder:**
1. Copy the entire `SixTerminal` folder to the target Windows machine
2. Place it anywhere (Desktop, Documents, USB drive, etc.)

---

### Step 2: Install Python (One-Time, 5 minutes)
**Only needed if Python isn't already installed**

1. Download Python 3.11+ from: https://www.python.org/downloads/
2. Run the installer
3. ✅ **IMPORTANT:** Check "Add Python to PATH" during installation
4. Click "Install Now"
5. Restart your computer (recommended)

**To verify Python is installed:**
- Open Command Prompt (Win+R, type `cmd`)
- Type: `python --version`
- Should show: `Python 3.11.x` or higher

---

### Step 3: Run SixTerminal
1. Navigate to the `SixTerminal` folder
2. **Double-click `RUN_SIXTERMINAL.bat`**
3. First run will:
   - Create virtual environment (~30 seconds)
   - Install dependencies (~2-3 minutes)
   - Create `config.json` template
4. **Edit `config.json`** and add your OpenAI API key
5. **Double-click `RUN_SIXTERMINAL.bat` again**
6. Browser opens automatically to `http://localhost:8501`

---

## 🔑 API Key Setup

After first run, edit `config.json`:

```json
{
  "api_key": "sk-your-actual-openai-key-here",
  "api_base_url": null,
  "ai_model": "gpt-4-turbo"
}
```

**Get your OpenAI API key:**
- Go to: https://platform.openai.com/api-keys
- Create new key
- Copy and paste into `config.json`

---

## 📁 Folder Structure

```
SixTerminal/
├── RUN_SIXTERMINAL.bat    ← Double-click this to start
├── config.json             ← Your API key goes here
├── requirements.txt        ← Dependencies list
├── src/                    ← Application code
│   ├── app.py
│   ├── parser.py
│   ├── copilot.py
│   └── ...
├── .venv/                  ← Virtual environment (auto-created)
└── .persistent_data/       ← Uploaded XER files (auto-created)
```

---

## 🎯 For Work Demos

### Sharing with Colleagues:

**Method 1 - USB/Network Drive:**
1. Copy entire `SixTerminal` folder to USB or shared drive
2. Share the folder
3. Each person runs `RUN_SIXTERMINAL.bat` on their machine
4. Each person needs their own API key in `config.json`

**Method 2 - ZIP File:**
1. Zip the entire `SixTerminal` folder
2. Email or share via Teams/Slack
3. Recipient extracts and runs `RUN_SIXTERMINAL.bat`

**Method 3 - Git Clone (For Tech-Savvy Users):**
```bash
git clone https://github.com/bloXbandit/SixTerminal.git
cd SixTerminal
# Double-click RUN_SIXTERMINAL.bat
```

---

## 🔧 Troubleshooting

### "Python is not installed or not in PATH"
- Install Python from python.org
- Make sure "Add Python to PATH" was checked
- Restart computer
- Try again

### "Failed to install dependencies"
- Check internet connection
- Run Command Prompt as Administrator
- Navigate to SixTerminal folder
- Run: `python -m pip install --upgrade pip`
- Run: `pip install -r requirements.txt`

### "Port 8501 is already in use"
- Another Streamlit app is running
- Close other terminal windows
- Or change port in the .bat file: `streamlit run src/app.py --server.port 8502`

### Browser doesn't open automatically
- Manually open browser
- Go to: `http://localhost:8501`

### App runs but AI Copilot doesn't work
- Check `config.json` has valid OpenAI API key
- Verify API key at: https://platform.openai.com/api-keys
- Check API key has credits/billing enabled

---

## 💡 Tips

**Updating the App:**
- Pull latest changes from GitHub
- Or replace `src/` folder with updated version
- No need to reinstall dependencies

**Multiple Versions:**
- Keep different folders for different versions
- Each has its own `.venv` and config

**Offline Use:**
- App works offline for XER parsing and charts
- AI Copilot requires internet (OpenAI API)

**Performance:**
- First run: 3-5 minutes (setup)
- Subsequent runs: 10-15 seconds (startup)
- Large XER files (10k+ activities): 30-60 seconds to load

---

## 📊 System Requirements

- **OS:** Windows 10 or 11
- **RAM:** 4 GB minimum, 8 GB recommended
- **Disk:** 1 GB free space
- **Internet:** Required for AI Copilot features
- **Python:** 3.8+ (3.11 recommended)

---

## 🆘 Support

**Issues or Questions:**
- GitHub Issues: https://github.com/bloXbandit/SixTerminal/issues
- Check logs in terminal window for error messages
- Include error messages when reporting issues

---

## ✅ Success Checklist

- [ ] Python installed with PATH enabled
- [ ] `RUN_SIXTERMINAL.bat` runs without errors
- [ ] `config.json` has valid API key
- [ ] Browser opens to SixTerminal dashboard
- [ ] Can upload .xer file successfully
- [ ] Dashboard displays project data
- [ ] AI Copilot responds to questions

**You're ready to demo! 🎉**
