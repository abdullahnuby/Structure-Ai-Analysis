@echo off
setlocal
where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama was not found.
  echo Install it from https://ollama.com/download/windows and start it, then run this file again.
  pause
  exit /b 1
)
echo Recommended local agent model for an 8 GB RAM computer: Qwen3.5 4B Q4_K_M.
echo The model download is about 3.3 GB. Runtime memory also depends on context and other apps.
echo If the 4B model is too slow or memory is insufficient, use qwen3.5:2b-q4_K_M as a weaker fallback.
echo.
ollama pull qwen3.5:4b-q4_K_M
if errorlevel 1 (
  echo The recommended model download failed.
  echo You can try the smaller fallback: ollama pull qwen3.5:2b-q4_K_M
  pause
  exit /b 1
)
echo.
echo Done. Open Structural Studio and run the real model + tool-call test.
echo A text-only reply is not considered sufficient for the engineering agent.
pause
