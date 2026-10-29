@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environment not found. Run setup_windows.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python run_frame2d.py --model examples\demo_frame2d.json --out output\frame2d_demo
if errorlevel 1 (
  echo Frame analysis failed. Review the message above.
  pause
  exit /b 1
)
echo Demo analysis and downloadable files are in output\frame2d_demo
pause
