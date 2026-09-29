@echo off
REM ============================================================
REM  JARVIS - build a standalone Windows executable
REM  Output: dist\JARVIS\JARVIS.exe
REM ============================================================
setlocal
cd /d "%~dp0"
title Building JARVIS

if not exist ".venv\Scripts\python.exe" (
    echo  Run run_jarvis.bat once before building, so the venv exists.
    pause
    exit /b 1
)
call ".venv\Scripts\activate.bat"

echo  Installing build tools...
pip install pyinstaller >nul

echo  Generating the application icon...
python assets\make_icon.py

echo  Making sure the wake-word model is bundled...
python scripts\download_models.py

echo.
echo  Building - this takes several minutes and produces a large folder
echo  because Whisper and onnxruntime are bundled.
echo.
pyinstaller jarvis.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo  BUILD FAILED. See the messages above.
    pause
    exit /b 1
)

echo.
echo  Done. Your build is in:  dist\JARVIS\JARVIS.exe
echo  Copy the whole dist\JARVIS folder to move it to another computer.
echo.
pause
endlocal
