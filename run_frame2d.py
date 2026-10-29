from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from structural_engine.frame2d_outputs import run_frame2d_pipeline

def main() -> int:
    parser = argparse.ArgumentParser(description="Experimental 2D linear-elastic frame solver; not a building design tool.")
    parser.add_argument("--model", default="examples/demo_frame2d.json", help="Input frame model JSON")
    parser.add_argument("--out", default="output/frame2d_demo", help="Output folder")
    args = parser.parse_args()
    try:
        model = json.loads(Path(args.model).read_text(encoding="utf-8-sig")); result = run_frame2d_pipeline(model, args.out)
    except Exception as exc:
        print(f"FRAME ANALYSIS FAILED: {exc}", file=sys.stderr); return 1
    analysis = result["result"]
    max_u = max((abs(n["ux_mm"]) for n in analysis["node_results"]), default=0.0)
    max_v = max((abs(n["uy_mm"]) for n in analysis["node_results"]), default=0.0)
    print("2D FRAME ANALYSIS COMPLETED (linear elastic; single load case)")
    print(f"Nodes: {analysis['node_count']} | Elements: {analysis['element_count']}")
    print(f"Max |ux|: {max_u:.6f} mm | Max |uy|: {max_v:.6f} mm")
    print(f"Equilibrium: {analysis['equilibrium']['equilibrium_check']} | relative residual {analysis['equilibrium']['relative_residual_norm']:.3e}")
    print(f"PDF: {result['pdf_path']}\nDXF: {result['dxf_path']}\nZIP: {result['zip_path']}")
    print("RELEASE: NOT FOR CONSTRUCTION; no RC design, Egyptian-code checks, or reinforcement design.")
    return 0
if __name__ == "__main__": raise SystemExit(main())