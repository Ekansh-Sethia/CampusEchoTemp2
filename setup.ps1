# CampusEcho - Automated 1-Click Environment Setup (PowerShell)
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  CampusEcho - Automated 1-Click Environment Setup" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# 1. Check Python installation
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[ERROR] Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.10+ from python.org and check 'Add Python to PATH'."
    exit 1
}

# 2. Create .venv
Write-Host "[1/4] Creating virtual environment (.venv)..." -ForegroundColor Yellow
if (-not (Test-Path ".venv")) {
    python -m venv .venv
} else {
    Write-Host ".venv already exists, reusing existing virtual environment." -ForegroundColor Green
}

# 3. Install dependencies
Write-Host "[2/4] Installing exact dependencies from requirements.txt..." -ForegroundColor Yellow
& .venv\Scripts\python -m pip install --upgrade pip
& .venv\Scripts\pip install -r requirements.txt

# 4. Generate test assets
Write-Host "[3/4] Generating synthetic test frames and assets..." -ForegroundColor Yellow
& .venv\Scripts\python tests\generate_test_frames.py

# 5. Run test verification
Write-Host "[4/4] Verifying installation with automated test suite..." -ForegroundColor Yellow
& .venv\Scripts\python -m pytest tests/ -v

Write-Host "========================================================" -ForegroundColor Green
Write-Host "  CampusEcho Setup Complete!" -ForegroundColor Green
Write-Host "  To test routing:     .venv\Scripts\python demo_phase1.py"
Write-Host "  To test perception:  .venv\Scripts\python demo_phase2.py --source 0"
Write-Host "  To run API docs:     .venv\Scripts\python -m uvicorn src.main:app --reload"
Write-Host "========================================================" -ForegroundColor Green
