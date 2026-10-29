@echo off
setlocal
cd /d "%~dp0"
echo === Structural Studio: preparing local Python environment ===
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher (py) was not found. Install Python 3.11+ from https://www.python.org/downloads/windows/
  pause
  exit /b 1
)
py -3 -m venv .venv
if errorlevel 1 goto error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto error
python -m pip install -r requirements.txt
if errorlevel 1 goto error
echo.
echo Setup finished. Run run_app.bat to launch the app.
pause
exit /b 0
:error
echo.
echo Setup failed. Check the error above and your internet connection.
pause
exit /b 1
