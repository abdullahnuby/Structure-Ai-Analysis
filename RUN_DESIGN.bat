@echo off
rem Usage: RUN_DESIGN.bat examples\design\beam_3span.json
if "%~1"=="" (echo Usage: RUN_DESIGN.bat file.json & exit /b 2)
python run_design.py %*
