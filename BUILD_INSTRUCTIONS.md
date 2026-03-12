# Building SixTerminal Standalone Executable

## 🎯 Goal
Create a standalone Windows `.exe` that runs without Python installation.

---

## 📋 Prerequisites

**On the Windows Build Machine:**
- Windows 10 or 11
- Python 3.8+ installed
- 2 GB free disk space
- 30-45 minutes for build process

---

## 🚀 Build Steps

### Step 1: Get the Code
```bash
git clone https://github.com/bloXbandit/SixTerminal.git
cd SixTerminal
```

### Step 2: Run the Build Script
**Double-click `BUILD_EXE.bat`**

This will:
1. Create virtual environment
2. Install all dependencies
3. Install PyInstaller
4. Build the executable (~10-15 minutes)

**OR manually:**
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
pyinstaller sixterminal.spec --clean
```

### Step 3: Find Your Executable
After successful build:
- Location: `dist/SixTerminal/`
- Main file: `SixTerminal.exe`
- Folder size: ~300-500 MB

---

## 📦 Distribution

### What to Share:
**Copy the entire `dist/SixTerminal` folder** - it contains:
- `SixTerminal.exe` - Main executable
- All required DLLs and dependencies
- Streamlit static files
- Python runtime

### How to Share:

**Option 1 - ZIP File:**
```bash
# Compress the folder
dist/SixTerminal/ → SixTerminal.zip
```
- Share via email, USB, network drive
- Recipient extracts and runs `SixTerminal.exe`

**Option 2 - Network/USB:**
- Copy `dist/SixTerminal` folder directly
- No compression needed

**Option 3 - Installer (Advanced):**
- Use Inno Setup or NSIS to create installer
- Creates Start Menu shortcuts
- Professional distribution

---

## 🔧 First Run Setup

**On the target machine:**

1. Extract/copy the `SixTerminal` folder
2. Create `config.json` in the same folder as `SixTerminal.exe`:
   ```json
   {
     "api_key": "sk-your-openai-key-here",
     "api_base_url": null,
     "ai_model": "gpt-4-turbo"
   }
   ```
3. Double-click `SixTerminal.exe`
4. Browser opens automatically to `http://localhost:8501`

---

## 🐛 Troubleshooting

### Build Fails with "Module not found"
**Solution:**
```bash
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
pyinstaller sixterminal.spec --clean
```

### Antivirus Blocks PyInstaller
**Solution:**
- Temporarily disable antivirus during build
- Add exception for PyInstaller
- Or build on different machine

### "Failed to execute script"
**Solution:**
- Run from Command Prompt to see error:
  ```bash
  cd dist\SixTerminal
  SixTerminal.exe
  ```
- Check if all DLLs are present
- Rebuild with `--clean` flag

### Executable is Too Large
**Current size: ~300-500 MB**

To reduce (optional):
1. Edit `sixterminal.spec`
2. Add more excludes:
   ```python
   excludes=[
       'matplotlib',
       'scipy',
       'numpy.distutils',
       'tkinter',
       'test',
       'unittest',
   ],
   ```
3. Rebuild

### Port 8501 Already in Use
**Solution:**
- Close other Streamlit instances
- Or modify startup to use different port

---

## 📊 Build Output Structure

```
dist/
└── SixTerminal/
    ├── SixTerminal.exe          ← Main executable
    ├── python311.dll            ← Python runtime
    ├── _internal/               ← Dependencies
    │   ├── streamlit/
    │   ├── pandas/
    │   ├── plotly/
    │   └── ...
    └── (various DLLs)
```

**Total folder size:** 300-500 MB
**Startup time:** 10-20 seconds (first run may be slower)

---

## ✅ Testing the Build

### Basic Test:
1. Run `SixTerminal.exe`
2. Should open browser automatically
3. Upload a `.xer` file
4. Verify dashboard displays
5. Test AI Copilot (requires API key)

### Full Test Checklist:
- [ ] Executable starts without errors
- [ ] Browser opens to localhost:8501
- [ ] Landing page displays correctly
- [ ] File upload works
- [ ] Dashboard renders with charts
- [ ] Stairway chart displays
- [ ] AI Copilot responds (with API key)
- [ ] Data persists on refresh

---

## 🔄 Updating the Executable

When you update the code:

1. Pull latest changes:
   ```bash
   git pull origin main
   ```

2. Rebuild:
   ```bash
   BUILD_EXE.bat
   ```

3. Redistribute the new `dist/SixTerminal` folder

---

## 💡 Tips

**For Faster Builds:**
- Use SSD for build directory
- Close other applications
- Disable antivirus temporarily

**For Smaller Size:**
- Remove unused dependencies from requirements.txt
- Add more excludes to spec file
- Use UPX compression (already enabled)

**For Better Performance:**
- Build on same Windows version as target machines
- Use Python 3.11 (faster than 3.8/3.9)
- Test on clean Windows VM first

**For Professional Distribution:**
- Add custom icon: `icon='path/to/icon.ico'` in spec file
- Create installer with Inno Setup
- Sign executable with code signing certificate
- Add version information

---

## 🆘 Support

**Build Issues:**
- Check PyInstaller docs: https://pyinstaller.org
- GitHub Issues: https://github.com/bloXbandit/SixTerminal/issues

**Common Build Errors:**
- Missing modules → Add to `hiddenimports` in spec file
- DLL not found → Check `binaries` in spec file
- Import errors → Add to `datas` in spec file

---

## 📝 Notes

**What Gets Bundled:**
- Python interpreter
- All pip packages
- Streamlit framework
- Your source code
- Static assets

**What Doesn't Get Bundled:**
- API keys (must be in config.json)
- Uploaded XER files (created at runtime)
- User data

**System Requirements (for built exe):**
- Windows 10/11
- 4 GB RAM (8 GB recommended)
- No Python installation needed ✅
- Internet for AI Copilot only

---

## ✨ Success!

After successful build, you'll have a **truly portable** SixTerminal:
- No Python installation required
- No pip install needed
- Just copy folder and run
- Perfect for demos and distribution

**Build time:** 10-15 minutes  
**Result:** Professional standalone application
