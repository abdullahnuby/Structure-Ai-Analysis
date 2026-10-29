@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environment not found. Run setup_windows.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python run_frame3d.py --model examples\demo_frame3d.json --out output\frame3d_demo
if errorlevel 1 (
  echo 3D frame analysis failed. Review the message above.
  pause
  exit /b 1
)
echo 3D demo outputs are in output\frame3d_demo
pause
