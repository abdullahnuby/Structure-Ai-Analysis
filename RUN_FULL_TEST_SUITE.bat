@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environment not found. Run setup_windows.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat

echo === 1/14 Python syntax compilation including local desktop workspace ===
python -m compileall -q desktop_server.py app.py structural_engine run_pipeline.py run_frame2d.py run_frame3d.py run_load_cases.py run_gravity_load_generation.py run_structural_system.py run_ai_preview_demo.py run_plate_shell.py run_plate_shell_benchmark.py run_punching_shear.py run_architectural_intake_demo.py run_ai_dxf_recommendation_smoke.py run_multistorey_stack_demo.py run_building_connectivity_preflight.py tests
if errorlevel 1 goto failed

echo === 2/14 Automated regression suite (solvers + AI agent + local API/UI workflow tests) ===
python -m pytest -q
if errorlevel 1 goto failed

echo === 3/14 2D frame analysis demo ===
python run_frame2d.py --model examples\demo_frame2d.json --out output\frame2d_demo
if errorlevel 1 goto failed

echo === 4/14 3D frame analysis demo ===
python run_frame3d.py --model examples\demo_frame3d.json --out output\frame3d_demo
if errorlevel 1 goto failed

echo === 5/14 DXF drafting pipeline ===
python run_pipeline.py --model examples\demo_project.json --dxf examples\demo_architecture.dxf --out output\drafting_demo
if errorlevel 1 goto failed

echo === 6/14 Multi-load-case and user-combination demo ===
python run_load_cases.py --model examples\demo_load_cases.json --out output\load_cases_demo
if errorlevel 1 goto failed

echo === 7/14 Gravity self-weight and slab beam-load generation demo ===
python run_gravity_load_generation.py --model examples\demo_gravity_load_generation.json --out output\gravity_load_generation_demo
if errorlevel 1 goto failed

echo === 8/14 Structural-system catalogue and preliminary load accounting ===
if not exist output\structural_systems mkdir output\structural_systems
for %%F in (examples\structural_systems\*.json) do (
  echo -- %%~nF
  python run_structural_system.py --model "%%F" --out "output\structural_systems\%%~nF"
  if errorlevel 1 goto failed
)

echo === 9/14 AI-agent context preparation (DXF preview only; no model inference) ===
python run_ai_preview_demo.py --dxf examples\demo_architecture.dxf --out output\ai_copilot_demo
if errorlevel 1 goto failed

echo === 10/14 Shell/Plate Q4 analysis and analytical mesh-convergence benchmark ===
python run_plate_shell.py --model examples\demo_plate_shell.json --out output\plate_shell_demo
if errorlevel 1 goto failed
python run_plate_shell_benchmark.py --out output\plate_shell_benchmark
if errorlevel 1 goto failed

echo === 11/14 Punching-shear geometry/demand-only pre-check ===
python run_punching_shear.py --input examples\demo_punching_shear.json --out output\punching_shear_demo
if errorlevel 1 goto failed

echo === 12/14 Architectural DXF intake -> reviewed structural candidate (synthetic fixture) ===
python run_architectural_intake_demo.py --out output\architectural_intake_demo
if errorlevel 1 goto failed

echo === 13/14 Multi-storey candidate: ground + repeated plans + levels + basement proxy checks ===
python run_multistorey_stack_demo.py --out output\multistorey_stack_demo
if errorlevel 1 goto failed

echo === 14/14 Building connectivity preflight: beam ends, column footprints, dimensions and blockers ===
python run_building_connectivity_preflight.py --out output\building_connectivity_preflight_v0_14_0
if errorlevel 1 goto failed

echo.
echo ALL AUTOMATED TESTS AND DEMO GENERATORS COMPLETED.
echo See output\structural_systems for all system readiness/load-accounting results.
echo See output\plate_shell_demo and output\plate_shell_benchmark for shell/plate reports and reference convergence.
echo See output\punching_shear_demo for b0 geometry and nominal demand only (no code capacity).
echo See output\architectural_intake_demo for DXF layer parsing, candidate floor model, overlay and hashes.
echo See output\multistorey_stack_demo for GF + N-1 typical floors, variable heights, street datum, basement and vertical continuity checks.
echo See output\building_connectivity_preflight_v0_14_0 for beam-end connectivity, section-dimension checks, candidate graph, PDF/DXF/CSV/ZIP output and blockers.
echo Engineering-agent tool-calling, local FastAPI workspace, DXF-to-building workflow, project gates, UI source readability and simplified single-primary-action dashboard are covered by pytest (step 2).
echo Live Ollama inference and real Windows browser interaction must be smoke-tested separately after local setup. The default run_app.bat launches the local web workspace; run_legacy_streamlit.bat retains the previous UI for troubleshooting.
echo.
echo Punching-shear outputs are geometry/demand only; no ECP capacity or pass/fail is implemented.
echo IMPORTANT: all design/analysis artifacts remain experimental and NOT FOR CONSTRUCTION.
pause
exit /b 0

:failed
echo.
echo TEST SUITE FAILED. Read the error above. Do not use outputs for design or construction.
pause
exit /b 1
