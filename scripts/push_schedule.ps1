# CampusEcho Hackathon Push Schedule Helper
# Usage:
#   .\scripts\push_schedule.ps1 -Stage 1
#   .\scripts\push_schedule.ps1 -Stage 2
#   ... up to -Stage 7
#
# Target Repo: D:\Stick-s-Disciples
# Source Repo: D:\CampusEchoTemp2

param (
    [Parameter(Mandatory=$true)]
    [ValidateRange(1, 7)]
    [int]$Stage,
    [string]$SourceDir = "D:\CampusEchoTemp2",
    [string]$TargetDir = "D:\Stick-s-Disciples"
)

if (-not (Test-Path $TargetDir)) {
    Write-Error "Target directory '$TargetDir' does not exist. Please check the path."
    exit 1
}

function Copy-FilesSafe {
    param([string]$SrcRel, [string]$DstRel)
    $src = Join-Path $SourceDir $SrcRel
    $dst = Join-Path $TargetDir $DstRel
    if (Test-Path $src) {
        $parent = Split-Path $dst -Parent
        if (-not (Test-Path $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        Copy-Item -Path $src -Destination $dst -Recurse -Force
        Write-Host "  [+] Copied: $SrcRel" -ForegroundColor Green
    } else {
        Write-Warning "Source not found: $src"
    }
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " Running Push Stage $Stage to $TargetDir" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

switch ($Stage) {
    1 {
        Write-Host "Stage 1: Project Scaffolding & Setup" -ForegroundColor Yellow
        Copy-FilesSafe ".gitignore" ".gitignore"
        Copy-FilesSafe "README.md" "README.md"
        Copy-FilesSafe "requirements.txt" "requirements.txt"
        Copy-FilesSafe "setup.bat" "setup.bat"
        Copy-FilesSafe "setup.ps1" "setup.ps1"
        Copy-FilesSafe "config\reference_dimensions.json" "config\reference_dimensions.json"
        Copy-FilesSafe "src\__init__.py" "src\__init__.py"
        Copy-FilesSafe "tests\__init__.py" "tests\__init__.py"
        $commitMsg = "feat: initialize project scaffolding, dependencies, and reference dimension configs"
    }
    2 {
        Write-Host "Stage 2: Core Topological Graph & Dijkstra Routing Engine" -ForegroundColor Yellow
        Copy-FilesSafe "data\campus_graph.json" "data\campus_graph.json"
        Copy-FilesSafe "src\routing\__init__.py" "src\routing\__init__.py"
        Copy-FilesSafe "src\routing\graph.py" "src\routing\graph.py"
        Copy-FilesSafe "src\routing\router.py" "src\routing\router.py"
        Copy-FilesSafe "demo_phase1.py" "demo_phase1.py"
        Copy-FilesSafe "tests\test_routing.py" "tests\test_routing.py"
        $commitMsg = "feat(routing): implement Dijkstra pathfinder with dynamic penalty weights and campus graph loader"
    }
    3 {
        Write-Host "Stage 3: Perception & Obstacle Detection Engine" -ForegroundColor Yellow
        Copy-FilesSafe "src\perception\__init__.py" "src\perception\__init__.py"
        Copy-FilesSafe "src\perception\models.py" "src\perception\models.py"
        Copy-FilesSafe "src\perception\video_source.py" "src\perception\video_source.py"
        Copy-FilesSafe "src\perception\distance.py" "src\perception\distance.py"
        Copy-FilesSafe "src\perception\tracking.py" "src\perception\tracking.py"
        Copy-FilesSafe "src\perception\shadow_filter.py" "src\perception\shadow_filter.py"
        Copy-FilesSafe "src\perception\hazard_heuristics.py" "src\perception\hazard_heuristics.py"
        Copy-FilesSafe "src\perception\detector.py" "src\perception\detector.py"
        Copy-FilesSafe "demo_phase2.py" "demo_phase2.py"
        Copy-FilesSafe "tests\test_perception.py" "tests\test_perception.py"
        Copy-FilesSafe "tests\generate_test_frames.py" "tests\generate_test_frames.py"
        $commitMsg = "feat(perception): add YOLOv8 obstacle detector, geometric distance estimator, shadow filter, and hazard heuristics"
    }
    4 {
        Write-Host "Stage 4: Decision Engine & Hazard Memory" -ForegroundColor Yellow
        Copy-FilesSafe "src\decision\__init__.py" "src\decision\__init__.py"
        Copy-FilesSafe "src\decision\confidence_policy.py" "src\decision\confidence_policy.py"
        Copy-FilesSafe "src\decision\hazard_memory.py" "src\decision\hazard_memory.py"
        Copy-FilesSafe "src\db\__init__.py" "src\db\__init__.py"
        Copy-FilesSafe "src\db\schema.py" "src\db\schema.py"
        Copy-FilesSafe "src\db\obstacle_store.py" "src\db\obstacle_store.py"
        Copy-FilesSafe "src\memory\__init__.py" "src\memory\__init__.py"
        Copy-FilesSafe "demo_phase3.py" "demo_phase3.py"
        Copy-FilesSafe "tests\test_decision.py" "tests\test_decision.py"
        Copy-FilesSafe "tests\test_db_and_sync.py" "tests\test_db_and_sync.py"
        $commitMsg = "feat(decision): add spatial hazard memory, confidence policy, SQLite cache, and dynamic reroute triggers"
    }
    5 {
        Write-Host "Stage 5: OCR Signpost Reader & Multi-Modal Notifications" -ForegroundColor Yellow
        Copy-FilesSafe "src\perception\text_reader.py" "src\perception\text_reader.py"
        Copy-FilesSafe "src\routing\landmark_matcher.py" "src\routing\landmark_matcher.py"
        Copy-FilesSafe "src\routing\navigator.py" "src\routing\navigator.py"
        Copy-FilesSafe "src\notifications\__init__.py" "src\notifications\__init__.py"
        Copy-FilesSafe "src\notifications\voice_engine.py" "src\notifications\voice_engine.py"
        Copy-FilesSafe "src\notifications\haptic_encoder.py" "src\notifications\haptic_encoder.py"
        Copy-FilesSafe "src\notifications\mode_router.py" "src\notifications\mode_router.py"
        Copy-FilesSafe "src\notifications\haptic_bridge.py" "src\notifications\haptic_bridge.py"
        Copy-FilesSafe "demo_phase4_5.py" "demo_phase4_5.py"
        Copy-FilesSafe "tests\test_ocr_localization.py" "tests\test_ocr_localization.py"
        Copy-FilesSafe "tests\test_notifications.py" "tests\test_notifications.py"
        Copy-FilesSafe "tests\generate_test_landmarks.py" "tests\generate_test_landmarks.py"
        $commitMsg = "feat(localization): add EasyOCR signpost reader, fuzzy landmark matcher, and dual audio/haptic alert system"
    }
    6 {
        Write-Host "Stage 6: Hardware Wristband Firmware, Dashboard API & System Entrypoints" -ForegroundColor Yellow
        Copy-FilesSafe "campusecho_haptic_wristband" "campusecho_haptic_wristband"
        Copy-FilesSafe "src\api\__init__.py" "src\api\__init__.py"
        Copy-FilesSafe "src\api\server.py" "src\api\server.py"
        Copy-FilesSafe "src\api\telemetry.py" "src\api\telemetry.py"
        Copy-FilesSafe "static" "static"
        Copy-FilesSafe "src\main.py" "src\main.py"
        Copy-FilesSafe "start.py" "start.py"
        Copy-FilesSafe "docs\HARDWARE_SETUP.md" "docs\HARDWARE_SETUP.md"
        Copy-FilesSafe "scripts\run_demo_scenarios.py" "scripts\run_demo_scenarios.py"
        Copy-FilesSafe "scripts\test_hardware.py" "scripts\test_hardware.py"
        Copy-FilesSafe "tests\test_api.py" "tests\test_api.py"
        Copy-FilesSafe "tests\test_integration.py" "tests\test_integration.py"
        Copy-FilesSafe "tests\test_haptic_bridge.py" "tests\test_haptic_bridge.py"
        $commitMsg = "feat(hardware): add ESP32 wristband firmware, FastAPI telemetry server, and live monitoring dashboard"
    }
    7 {
        Write-Host "Stage 7: Full SGSITS Campus Graph, Photos & Comprehensive Docs" -ForegroundColor Yellow
        Copy-FilesSafe "data\sgsits_campus_graph_full.json" "data\sgsits_campus_graph_full.json"
        Copy-FilesSafe "GS Photos" "GS Photos"
        Copy-FilesSafe "tests\test_sgsits_full_graph.py" "tests\test_sgsits_full_graph.py"
        Copy-FilesSafe "ARCHITECTURE.md" "ARCHITECTURE.md"
        Copy-FilesSafe "DESIGN_DECISIONS.md" "DESIGN_DECISIONS.md"
        Copy-FilesSafe "IMPLEMENTATION_PLAN.md" "IMPLEMENTATION_PLAN.md"
        $commitMsg = "docs: add full SGSITS campus navigation graph, multi-angle landmark photos, and architecture design docs"
    }
}

Write-Host "`nStaging files in Git..." -ForegroundColor Cyan
Push-Location $TargetDir
try {
    git add .
    $status = git status --porcelain
    if ($status) {
        Write-Host "Committing with message: '$commitMsg'" -ForegroundColor Green
        git commit -m $commitMsg
        Write-Host "Pushing to remote..." -ForegroundColor Green
        git push
        Write-Host "`n[✓] Stage $Stage pushed successfully!" -ForegroundColor Green
    } else {
        Write-Host "No changes detected to commit." -ForegroundColor Yellow
    }
} catch {
    Write-Error "Git command failed: $_"
} finally {
    Pop-Location
}
