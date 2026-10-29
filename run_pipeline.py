from __future__ import annotations
import argparse
from pathlib import Path
import sys
from structural_engine.pipeline import run_pipeline

def main() -> int:
    parser=argparse.ArgumentParser(description="Structural Studio local documentation pipeline (draft-only; no structural design).")
    parser.add_argument("--model", default="examples/demo_project.json", help="Path to a project model JSON")
    parser.add_argument("--out", default="output/demo_run", help="Output directory")
    parser.add_argument("--dxf", default=None, help="Optional architectural DXF to inspect and bundle")
    args=parser.parse_args()
    try: result=run_pipeline(args.model,args.out,args.dxf)
    except Exception as exc: print(f"PIPELINE FAILED: {exc}",file=sys.stderr); return 1
    print("PIPELINE COMPLETED"); print(f"Output directory: {result['output_dir']}"); print(f"Drawing PDF: {Path(result['output_dir']) / result['drawing_set']['pdf']}")
    print(f"Sheets: {result['drawing_set']['pages']} PDF pages; {len(result['drawing_set']['dxf_sheets'])} DXF files"); print("PDF/DXF checks: PASS")
    print("Construction release: BLOCKED (no building-wide structural analysis/design/reinforcement)"); print(f"ZIP package: {result['zip_path']}"); return 0
if __name__=="__main__": raise SystemExit(main())