from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

from structural_engine.ai_copilot import OllamaClient, OllamaUnavailable
from structural_engine.dxf_inspector import inspect_dxf_bytes
from structural_engine.engineering_agent import EngineeringAgent, build_engineering_tools

ROOT = Path(__file__).resolve().parent


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Live Ollama tool-calling smoke test on a fixed DEMO fixture only.")
    parser.add_argument("--model", default="qwen3.5:4b-q4_K_M", help="Installed local Ollama model (default: qwen3.5:4b-q4_K_M; use a smaller fallback only if necessary)")
    parser.add_argument("--out", default="output/engineering_agent_live_smoke", help="Output directory for this test run")
    args = parser.parse_args()

    client = OllamaClient()
    try:
        installed = client.list_models()
    except OllamaUnavailable as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    names = [str(item.get("name", "")) for item in installed]
    chosen = next((name for name in names if name == args.model), None)
    if not chosen:
        print(f"ERROR: model '{args.model}' is not installed. Available local models: {names}", file=sys.stderr)
        print(f"Run: ollama pull {args.model}", file=sys.stderr)
        return 2

    dxf_path = ROOT / "examples" / "demo_architecture.dxf"
    dxf_data = dxf_path.read_bytes()
    state = {
        "project_fields": {
            "project_name": "DEMO — live AI tool-call smoke test only",
            "project_number": "AGENT-SMOKE-DEMO",
            "location": "synthetic fixture",
            "building_use": "سكني",
            "stories_above_ground": 2,
            "story_height_m": 3.0,
            "specified_concrete_strength_MPa": 25.0,
            "specified_steel_yield_strength_MPa": 400.0,
            "code_reference_as_entered": "غير محدد — DEMO fixture",
            "soil_report_status": "غير متوفر",
            "soil_notes": "بيانات تجريبية اصطناعية فقط",
            "live_load_source_as_entered": "غير محدد — DEMO fixture",
            "lateral_load_basis_as_entered": "غير محدد — DEMO fixture",
        },
        "dxf_summary": inspect_dxf_bytes(dxf_data, dxf_path.name),
        "is_demo_project": True,
        # These permissions are hardcoded here solely for the named synthetic fixture.
        "allow_demo_analysis": True,
        "confirm_current_inputs": False,
        "regular_grid_confirmed": False,
        "demo_tool_flags": {"frame2d": True, "frame3d": True, "plate_shell": True, "punching_shear": True},
        "frame2d_model": read_json(ROOT / "examples" / "demo_frame2d.json"),
        "frame3d_model": read_json(ROOT / "examples" / "demo_frame3d.json"),
        "plate_shell_inputs": read_json(ROOT / "examples" / "demo_plate_shell.json"),
        "punching_inputs": read_json(ROOT / "examples" / "demo_punching_shear.json"),
        "selected_system_id": "rc_flat_plate",
        "selected_system_config": read_json(ROOT / "examples" / "structural_systems" / "rc_flat_plate.json"),
    }
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out = (ROOT / args.out / run_id).resolve()
    out.mkdir(parents=True, exist_ok=True)
    state["output_dir"] = str(out / "tool_outputs")
    runtime: dict[str, Any] = {"tool_results": {}, "artifacts": {}}
    tools = build_engineering_tools(state, runtime)
    prompt = (
        "هذا اختبار حي لوكيل الأدوات على بيانات DEMO اصطناعية فقط. "
        "ابدأ باستدعاء inspect_project_status، ثم استدعِ analyze_frame2d_model مرة واحدة. "
        "اقرأ نتيجة التحليل، ثم لخّص الأدوات التي استدعيتها، وأرقام الإزاحات/الاتزان إذا توفرت، "
        "واذكر بوضوح أنها تجربة برنامج وليست تصميمًا صالحًا للتنفيذ. لا تستدعِ أدوات أخرى."
    )
    try:
        result = EngineeringAgent(client=client, max_tool_calls=4, max_model_rounds=5).run(
            chosen, [{"role": "user", "content": prompt}], tools
        )
    except (OllamaUnavailable, ValueError) as exc:
        print(f"ERROR: live agent run failed: {exc}", file=sys.stderr)
        return 3

    (out / "agent_trace.json").write_text(json.dumps({
        "release": "0.18.0", "run_id": run_id, "model": chosen,
        "purpose": "LIVE_OLLAMA_TOOL_CALLING_SMOKE_TEST_DEMO_ONLY", "prompt": prompt,
        "final_text": result.final_text, "stopped_reason": result.stopped_reason,
        "tool_trace": result.trace, "not_for_construction": True,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    copied = []
    artifact_root = out / "artifacts"
    for group, entries in runtime.get("artifacts", {}).items():
        for name, data in entries.items():
            if not isinstance(data, bytes):
                continue
            target = artifact_root / group / name
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data); copied.append(target)
    tool_names = [str(item.get("tool", "")) for item in result.trace]
    success = "inspect_project_status" in tool_names and "analyze_frame2d_model" in tool_names
    report = {"result":"PASS" if success else "MODEL_DID_NOT_COMPLETE_EXPECTED_TOOL_SEQUENCE", "model":chosen,
              "tool_names":tool_names, "tool_statuses":[item.get("status") for item in result.trace],
              "final_text":result.final_text, "stopped_reason":result.stopped_reason,
              "artifact_files":[str(p.relative_to(out)).replace("\\", "/") for p in copied],
              "important":"This tests live model tool-calling only against named demo fixtures. It is not a structural design validation."}
    (out / "smoke_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = []
    for file in sorted(p for p in out.rglob("*") if p.is_file() and p.name != "manifest.json"):
        manifest.append({"path":str(file.relative_to(out)).replace("\\", "/"), "size_bytes":file.stat().st_size,
                         "sha256":hashlib.sha256(file.read_bytes()).hexdigest()})
    (out / "manifest.json").write_text(json.dumps({"release":"0.18.0","files":manifest,"not_for_construction":True}, indent=2), encoding="utf-8")
    bundle = out / "agent_live_smoke_package.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(p for p in out.rglob("*") if p.is_file() and p != bundle):
            zf.write(file, arcname=str(file.relative_to(out)).replace("\\", "/"))
    with zipfile.ZipFile(bundle) as zf:
        if zf.testzip():
            print("ERROR: output ZIP integrity failed", file=sys.stderr); return 4
    print(json.dumps(report, ensure_ascii=False, indent=2)); print(f"\nTrace/report/artifacts: {out}"); print(f"Bundle: {bundle}")
    return 0 if success else 5

if __name__ == "__main__": raise SystemExit(main())