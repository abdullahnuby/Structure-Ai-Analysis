@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environment not found. Run setup_windows.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python run_ai_dxf_recommendation_smoke.py --model qwen3.5:2b
if errorlevel 1 goto failed
echo.
echo LIVE AI DXF RECOMMENDATION SMOKE TEST PASSED.
echo Review output under output\ai_dxf_recommendation_smoke.
echo Synthetic fixture only. This is not a structural design validation.
pause
exit /b 0
:failed
echo LIVE AI DXF RECOMMENDATION SMOKE TEST FAILED OR DID NOT COMPLETE THE EXPECTED TOOL SEQUENCE.
echo Inspect smoke_report.json and agent_trace.json; do not infer structural design safety.
pause
exit /b 1
