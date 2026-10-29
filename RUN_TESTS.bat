@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environment not found. Run setup_windows.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pytest -q
if errorlevel 1 (
  echo Tests FAILED.
  pause
  exit /b 1
)
echo All tests passed.
pause
