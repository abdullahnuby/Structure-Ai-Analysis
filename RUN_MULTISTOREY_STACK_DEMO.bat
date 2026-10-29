@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environment not found. Run setup_windows.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python run_multistorey_stack_demo.py --out output\multistorey_stack_demo_v0_13_0
if errorlevel 1 goto failed
echo.
echo Demo complete. See output\multistorey_stack_demo_v0_13_0 for JSON, PNG, ZIP and SHA256 manifest.
echo The result is a geometric candidate only, not an analysis-ready or construction model.
pause
exit /b 0
:failed
echo Demo failed. Do not use its outputs for design or construction.
pause
exit /b 1
