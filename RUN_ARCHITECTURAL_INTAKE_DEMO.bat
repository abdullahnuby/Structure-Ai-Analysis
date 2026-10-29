@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environment not found. Run setup_windows.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python run_architectural_intake_demo.py --out output\architectural_intake_demo
if errorlevel 1 goto failed
echo.
echo DEMO COMPLETE. Open output\architectural_intake_demo\candidate_overlay.png and candidate_structural_floor.json.
echo This is a synthetic review-only example, not a structural design.
pause
exit /b 0
:failed
echo DXF intake demo failed. Do not use outputs for design or construction.
pause
exit /b 1
