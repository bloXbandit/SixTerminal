@echo off
REM SixTerminal Portable Launcher
REM Double-click this file to start SixTerminal

echo ========================================
echo    SixTerminal - P6 Analysis Tool
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo.
    echo Please install Python 3.8+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

echo [1/3] Checking Python installation...
python --version

REM Check if virtual environment exists
if not exist ".venv" (
    echo.
    echo [2/3] Creating virtual environment (first-time setup)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Activate virtual environment
echo.
echo [2/3] Activating environment...
call .venv\Scripts\activate.bat

REM Check if dependencies are installed
python -c "import streamlit" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [3/3] Installing dependencies (first-time setup, may take 2-3 minutes)...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
) else (
    echo [3/3] Dependencies already installed
)

REM Check for config file
if not exist "config.json" (
    echo.
    echo ========================================
    echo   FIRST TIME SETUP
    echo ========================================
    echo.
    echo Creating config.json template...
    echo Please edit config.json and add your OpenAI API key
    echo.
    (
        echo {
        echo   "api_key": "YOUR_OPENAI_API_KEY_HERE",
        echo   "api_base_url": null,
        echo   "ai_model": "gpt-4-turbo"
        echo }
    ) > config.json
    echo.
    echo Config file created! Edit config.json before running again.
    pause
    exit /b 0
)

REM Start the application
echo.
echo ========================================
echo   Starting SixTerminal...
echo ========================================
echo.
echo The app will open in your default browser
echo Press Ctrl+C to stop the server
echo.

streamlit run src/app.py

REM If streamlit exits, pause so user can see any errors
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Application exited with error code %errorlevel%
    pause
)
