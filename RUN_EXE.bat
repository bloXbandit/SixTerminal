@echo off
REM SixTerminal Launcher for Standalone EXE
REM Place this file in the same folder as SixTerminal.exe

echo ========================================
echo    SixTerminal - P6 Analysis Tool
echo ========================================
echo.

REM Check if config.json exists
if not exist "config.json" (
    echo Creating config.json template...
    echo.
    (
        echo {
        echo   "api_key": "YOUR_OPENAI_API_KEY_HERE",
        echo   "api_base_url": null,
        echo   "ai_model": "gpt-4-turbo"
        echo }
    ) > config.json
    echo Config file created!
    echo Please edit config.json and add your OpenAI API key
    echo.
    pause
    exit /b 0
)

REM Start the application
echo Starting SixTerminal...
echo The app will open in your default browser
echo Press Ctrl+C to stop the server
echo.

SixTerminal.exe

REM If exe exits with error, pause so user can see
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Application exited with error code %errorlevel%
    pause
)
