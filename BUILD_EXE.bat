@echo off
REM SixTerminal - Build Standalone EXE
REM Run this on a Windows machine to create the executable

echo ========================================
echo    SixTerminal EXE Builder
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/5] Checking Python installation...
python --version
echo.

REM Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo [2/5] Creating virtual environment...
    python -m venv .venv
) else (
    echo [2/5] Virtual environment already exists
)
echo.

REM Activate virtual environment
echo [3/5] Activating environment...
call .venv\Scripts\activate.bat
echo.

REM Install dependencies
echo [4/5] Installing dependencies (this may take 5-10 minutes)...
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
echo.

REM Build the executable
echo [5/5] Building executable (this may take 10-15 minutes)...
echo.
echo This will create a 'dist/SixTerminal' folder with the executable
echo.

pyinstaller sixterminal.spec --clean

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   BUILD SUCCESSFUL!
    echo ========================================
    echo.
    echo Your executable is in: dist\SixTerminal\
    echo.
    echo To distribute:
    echo   1. Copy the entire 'dist\SixTerminal' folder
    echo   2. Create config.json in that folder with API key
    echo   3. Run SixTerminal.exe
    echo.
    echo Folder size: ~300-500 MB
    echo.
) else (
    echo.
    echo ========================================
    echo   BUILD FAILED
    echo ========================================
    echo.
    echo Check the error messages above
    echo Common issues:
    echo   - Missing dependencies
    echo   - Antivirus blocking PyInstaller
    echo   - Insufficient disk space
    echo.
)

pause
