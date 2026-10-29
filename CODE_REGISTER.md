# Structural Studio — Code Register (v0.18.0)

## Main entry points
- `run_app.bat` starts the local desktop web workspace via `desktop_server.py`; `app.py` is the legacy Streamlit entry point retained for compatibility.
- `desktop_web/index.html`, `desktop_web/assets/app.css`, `desktop_web/assets/app.js`: self-contained Arabic RTL user interface.
- `desktop_server.py`: loopback-only local HTTP API for project state, DXF intake/review, building candidate generation and AI orchestration.

## Core modules
- `structural_engine/engineering_agent.py`: bounded Ollama tool-calling loop, explicit tool registry/argument validation, run trace and artifacts.
- `structural_engine/dxf_inspector.py`, `dxf_preview.py`, `dxf_structural_inference.py`: geometry/layer extraction, approximate preview, candidate element classification.
- `structural_engine/building_stack.py`, `building_model_preflight.py`, `model_builder.py`: multistorey geometry candidate and pre-analysis blockers.
- `structural_engine/frame2d.py`, `frame3d.py`: experimental linear elastic frame solvers.
- `structural_engine/plate_shell.py`: restricted rectangular Q4 plate/shell prototype with a limited reference benchmark.
- `structural_engine/load_cases.py`, `load_generation.py`, `punching_shear.py`: explicit load-case superposition, tributary gravity bookkeeping and punching-shear geometry/demand-only checks.
- `structural_engine/*_outputs.py`: reports and reproducible PDF/DXF/CSV/JSON/ZIP artifacts with hashes.

## Testing
- `tests/`: unit, regression and integration tests.
- `RUN_FULL_TEST_SUITE.bat`: Windows test-and-demo runner.
- `RUN_AI_AGENT_LIVE_SMOKE.bat`: separate test requiring Ollama and a downloaded model; test uses synthetic DEMO fixtures only.

## Non-negotiable engineering limits
- All system catalogue entries and geometry classifications are candidates, not validated engineering decisions.
- Frame and plate/shell solvers are experimental and limited to documented fixtures. Numerical equilibrium/test success does not verify a real building.
- Punching-shear module computes geometry and nominal demand only; no concrete resistance or ECP pass/fail is implemented.
- No complete ECP 203-2025 reinforced-concrete strength/serviceability design, lateral-system design, foundation design, bar detailing/BBS, or construction-ready drawing issue is implemented.
- All outputs are `NOT FOR CONSTRUCTION` and require independent review by a qualified structural engineer.
