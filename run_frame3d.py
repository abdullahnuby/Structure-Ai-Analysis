from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from structural_engine.frame3d_outputs import run_frame3d_pipeline

def main() -> int:
    p=argparse.ArgumentParser(description="Experimental 3D linear-elastic space-frame solver; no RC code design.")
    p.add_argument("--model",default="examples/demo_frame3d.json"); p.add_argument("--out",default="output/frame3d_demo"); args=p.parse_args()
    try:
        model=json.loads(Path(args.model).read_text(encoding="utf-8-sig")); result=run_frame3d_pipeline(model,args.out)
    except Exception as exc:
        print(f"3D FRAME ANALYSIS FAILED: {exc}",file=sys.stderr); return 1
    r=result["result"]; maxima={axis:max((abs(n[f"u{axis}_mm"]) for n in r["node_results"]),default=0.0) for axis in ("x","y","z")}
    print("3D SPACE FRAME ANALYSIS COMPLETED (linear elastic, one load case)")
    print(f"Nodes: {r['node_count']} | Elements: {r['element_count']}")
    print(f"Max |ux|: {maxima['x']:.5f} mm | |uy|: {maxima['y']:.5f} mm | |uz|: {maxima['z']:.5f} mm")
    print(f"Global equilibrium: {r['equilibrium']['equilibrium_check']} | residual {r['equilibrium']['relative_residual_norm']:.3e}")
    print(f"PDF: {result['pdf_path']}\nDXF: {result['dxf_path']}\nZIP: {result['zip_path']}")
    print("RELEASE: NOT FOR CONSTRUCTION; no Egyptian-code load combinations, RC design or reinforcement.")
    return 0
if __name__=="__main__": raise SystemExit(main())