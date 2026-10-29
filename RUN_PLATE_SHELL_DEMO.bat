@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environment not found. Run setup_windows.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python run_plate_shell.py --model examples\demo_plate_shell.json --out output\plate_shell_demo
if errorlevel 1 goto failed
python run_plate_shell_benchmark.py --out output\plate_shell_benchmark
if errorlevel 1 goto failed
echo.
echo Open output\plate_shell_demo and output\plate_shell_benchmark to inspect reports and data.
echo NOT FOR CONSTRUCTION.
pause
exit /b 0
:failed
echo Plate/Shell demo or benchmark FAILED. Do not use outputs for design.
pause
exit /b 1
