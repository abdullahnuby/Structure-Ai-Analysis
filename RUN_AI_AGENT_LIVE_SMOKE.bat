@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environment not found. Run setup_windows.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat

echo This is a LIVE Ollama tool-calling test against fixed DEMO fixtures only.
echo It does not read or modify your real project model and is NOT a design validation.
echo Recommended model: qwen3.5:4b-q4_K_M (better tool planning, tighter RAM use on 8 GB).
echo If you intentionally installed only the smaller fallback, edit this command to qwen3.5:2b-q4_K_M.
python run_engineering_agent_live_smoke.py --model qwen3.5:4b-q4_K_M
set RESULT=%ERRORLEVEL%
echo.
if not "%RESULT%"=="0" (
  echo The selected model did not complete the expected tool sequence or Ollama failed.
  echo See any generated output under output\engineering_agent_live_smoke.
) else (
  echo Live local tool-calling smoke test PASSED on DEMO fixtures only.
)
pause
exit /b %RESULT%
