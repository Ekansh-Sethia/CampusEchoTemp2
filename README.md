# CampusEcho

An Explainable, Memory-Driven Indoor & Campus Navigation Assistant for Visually Impaired Students.

---

## 🚀 1-Click Setup for Collaborators

When you clone this repository onto your machine:

1. **Double-click `setup.bat`** (or in PowerShell run `.\setup.ps1`).
2. The script will automatically:
   - Create your local `.venv` virtual environment tailored to your machine.
   - Install all required dependencies from `requirements.txt`.
   - Generate test frames in `data/test_frames/`.
   - Run the automated test suite to confirm everything works.

---

## 🧪 Testing Modules

### Phase 1: Campus Graph & Dijkstra Routing
```powershell
# Interactive CLI demo showing routes and obstacle rerouting
.venv\Scripts\python demo_phase1.py

# Run FastAPI Swagger API Docs
.venv\Scripts\python -m uvicorn src.main:app --reload --port 8000
# Open browser at: http://127.0.0.1:8000/docs
```

### Phase 2: Real-Time Perception Loop (YOLOv8n + Hazard Detection)
```powershell
# Run with synthetic test frames (stairs, potholes, clear hall, walls)
.venv\Scripts\python demo_phase2.py --source test_frames

# Run with live laptop webcam
.venv\Scripts\python demo_phase2.py --source 0

# Run with a recorded video file
.venv\Scripts\python demo_phase2.py --source path/to/video.mp4
```

### Run All Automated Tests
```powershell
.venv\Scripts\python -m pytest tests/ -v
```
