from __future__ import annotations
import argparse, json
from pathlib import Path
from structural_engine.punching_shear import analyze_punching_shear_demand
from structural_engine.punching_shear_outputs import run_punching_shear_pipeline

def main() -> None:
    parser = argparse.ArgumentParser(description="Punching-shear geometry/demand pre-check only; no code capacity verdict.")
    parser.add_argument("--input", default="examples/demo_punching_shear.json"); parser.add_argument("--out", default="output/punching_shear_demo"); args = parser.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8")); result = analyze_punching_shear_demand(data); out = run_punching_shear_pipeline(result, args.out)
    print(json.dumps({"status": result["status"], "b0_mm": result["geometry"]["critical_perimeter_b0_mm"], "Vu_net_kN": result["loads"]["net_punching_shear_Vu_kN"], "v_nominal_MPa": result["demand"]["nominal_concentric_shear_stress_MPa"], "capacity_status": result["code_capacity"]["status"], **out}, indent=2))
if __name__ == "__main__": main()
