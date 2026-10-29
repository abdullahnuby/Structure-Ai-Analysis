@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environment not found. Run setup_windows.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python run_punching_shear.py --input examples\demo_punching_shear.json --out output\punching_shear_demo
if errorlevel 1 goto failed
echo.
echo Review output\punching_shear_demo. This is geometry/demand only; no code capacity or PASS/FAIL.
echo NOT FOR CONSTRUCTION.
pause
exit /b 0
:failed
echo Punching-shear prototype FAILED. Do not use outputs for design or construction.
pause
exit /b 1
