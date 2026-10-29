from __future__ import annotations
import argparse, json
from pathlib import Path
from structural_engine.gravity_generation_outputs import run_gravity_generation_pipeline

def main() -> int:
    parser=argparse.ArgumentParser(description='Generate member self-weight and explicit tributary-width slab gravity cases.')
    parser.add_argument('--model',default='examples/demo_gravity_load_generation.json'); parser.add_argument('--out',default='output/gravity_load_generation_demo'); args=parser.parse_args()
    data=json.loads(Path(args.model).read_text(encoding='utf-8-sig')); result=run_gravity_generation_pipeline(data,args.out); summary=result['summary']
    print(json.dumps({'status':summary['status'],'slab_count':summary['slab_count'],'total_slabs_area_m2':summary['total_slabs_area_m2'],'total_slab_dead_load_kN':summary['total_slab_dead_load_kN'],'total_slab_live_load_kN':summary['total_slab_live_load_kN'],'zip_path':result['zip_path'],'artifact_count':len(result['artifacts'])},ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())