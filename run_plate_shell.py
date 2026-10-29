from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from structural_engine.plate_shell import build_rectangular_plate_model
from structural_engine.plate_shell_outputs import run_plate_shell_pipeline

def main() -> int:
    p=argparse.ArgumentParser(description="Prototype planar Q4 shell/plate analysis; no ECP design or punching check.")
    p.add_argument("--model",default="examples/demo_plate_shell.json",help="Input JSON with geometry/material/load/support inputs."); p.add_argument("--out",default="output/plate_shell_demo"); args=p.parse_args()
    try:
        data=json.loads(Path(args.model).read_text(encoding="utf-8-sig")); model=build_rectangular_plate_model(**data) if "nodes" not in data else data; result=run_plate_shell_pipeline(model,args.out)
    except Exception as exc: print(f"PLATE/SHELL ANALYSIS FAILED: {exc}",file=sys.stderr); return 1
    r=result["result"]
    print("PLANAR Q4 SHELL/PLATE ANALYSIS COMPLETED — RESEARCH PROTOTYPE")
    print(f"Nodes: {r['mesh']['node_count']} | Q4 elements: {r['mesh']['element_count']} | Area: {r['mesh']['total_area_m2']:.4f} m²")
    print(f"Max |uz|: {r['max_abs_uz_m']*1000:.5f} mm | ΣFz: {r['equilibrium']['sum_Fz_kN']:.3e} kN | Residual: {r['equilibrium']['relative_free_dof_residual']:.3e}")
    if result["reference"]: print(f"Kirchhoff/Navier square-plate reference: {result['reference']['center_deflection_m']*1000:.5f} mm (thin-plate reference; shear effects may differ)")
    print(f"PDF: {result['pdf_path']}\nDXF: {result['dxf_path']}\nZIP: {result['zip_path']}"); print("RELEASE: NOT FOR CONSTRUCTION; no ECP resistance/serviceability, punching shear or reinforcement design."); return 0
if __name__=="__main__": raise SystemExit(main())