@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environment not found. Run setup_windows.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python run_building_connectivity_preflight.py --out output\building_connectivity_preflight_v0_14_0
if errorlevel 1 goto failed
echo.
echo Connectivity preflight generated and checked.
echo See output\building_connectivity_preflight_v0_14_0 for JSON, PDF, DXF, ZIP and manifest.
echo This is geometric/topological QA only; analysis remains blocked.
pause
exit /b 0
:failed
echo Connectivity preflight demo failed. Do not use outputs for design or construction.
pause
exit /b 1
