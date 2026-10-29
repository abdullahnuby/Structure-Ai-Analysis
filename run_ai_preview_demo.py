"""Create a local PNG preview of the sample DXF without requiring Ollama."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from structural_engine.dxf_inspector import inspect_dxf_bytes
from structural_engine.dxf_preview import render_dxf_preview_png

def main() -> int:
    parser=argparse.ArgumentParser(description="Structural Studio local AI preview fixture")
    parser.add_argument("--dxf",default="examples/demo_architecture.dxf")
    parser.add_argument("--out",default="output/ai_copilot_demo")
    args=parser.parse_args(); src=Path(args.dxf); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    data=src.read_bytes(); summary=inspect_dxf_bytes(data,src.name); png=render_dxf_preview_png(data,src.name)
    (out/"dxf_ai_preview.png").write_bytes(png)
    (out/"dxf_context_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    manifest={"status":"PREVIEW_READY_AI_NOT_RUN","source_dxf":src.name,"preview_file":"dxf_ai_preview.png","preview_sha256":hashlib.sha256(png).hexdigest(),"entity_count":summary["modelspace_entity_count"],"layer_count":len(summary["layers"]),"note":"Preview prepared; no model was called."}
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps(manifest,ensure_ascii=False,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())