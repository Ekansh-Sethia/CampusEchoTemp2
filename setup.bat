@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo   CampusEcho - Automated 1-Click Environment Setup
echo ========================================================

:: 1. Check Python installation
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in your PATH.
    echo Please install Python 3.10+ from python.org and check "Add Python to PATH".
    pause
    exit /b 1
)

echo [1/4] Creating virtual environment (.venv)...
if not exist ".venv" (
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create .venv.
        pause
        exit /b 1
    )
) else (
    echo .venv already exists, reusing existing virtual environment.
)

echo [2/4] Installing exact dependencies from requirements.txt...
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo [3/4] Generating synthetic test frames and assets...
.venv\Scripts\python tests\generate_test_frames.py

echo [4/4] Verifying installation with automated test suite...
.venv\Scripts\python -m pytest tests\ -v

echo ========================================================
echo   CampusEcho Setup Complete!
echo   To test routing:     .venv\Scripts\python demo_phase1.py
echo   To test perception:  .venv\Scripts\python demo_phase2.py --source 0
echo   To run API docs:     .venv\Scripts\python -m uvicorn src.main:app --reload
echo ========================================================
pause
