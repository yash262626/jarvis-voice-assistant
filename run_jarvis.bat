@echo off
REM ============================================================
REM  JARVIS - start script
REM  Creates the virtual environment on first run, then launches.
REM ============================================================
setlocal
cd /d "%~dp0"
title JARVIS Voice Assistant

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  First run detected - creating the virtual environment...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if errorlevel 1 (
        echo.
        echo  ERROR: Python 3.10-3.12 was not found on this computer.
        echo  Install it from https://www.python.org/downloads/windows/
        echo  and tick "Add python.exe to PATH" during setup.
        echo.
        pause
        exit /b 1
    )
    call ".venv\Scripts\activate.bat"
    echo  Installing dependencies. This takes a few minutes the first time...
    python -m pip install --upgrade pip >nul
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  ERROR: dependency installation failed. Check your internet
        echo  connection and run this file again.
        echo.
        pause
        exit /b 1
    )
    echo  Downloading the "Hey Jarvis" wake-word model...
    python scripts\download_models.py
) else (
    call ".venv\Scripts\activate.bat"
)

python -c "import sounddevice, PySide6" 2>nul
if errorlevel 1 (
    echo  Dependencies look incomplete - reinstalling...
    pip install -r requirements.txt
)

echo.
echo  Starting JARVIS. Say "Hey Jarvis" or press Ctrl+Alt+J.
echo  Close this window to stop the assistant.
echo.
python main.py %*

if errorlevel 1 (
    echo.
    echo  JARVIS exited with an error. The details are in logs\jarvis.log
    echo.
    pause
)
endlocal
