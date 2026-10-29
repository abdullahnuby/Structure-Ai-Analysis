from __future__ import annotations
import argparse, json
from pathlib import Path
from structural_engine.load_case_outputs import run_load_case_pipeline

def main() -> int:
    parser = argparse.ArgumentParser(description='Run explicit user-defined 3D load cases and linear combinations.')
    parser.add_argument('--model', default='examples/demo_load_cases.json'); parser.add_argument('--out', default='output/load_cases_demo'); args = parser.parse_args()
    package = json.loads(Path(args.model).read_text(encoding='utf-8-sig')); result = run_load_case_pipeline(package, args.out)
    print(json.dumps({'status': result['analysis']['status'], 'load_cases': len(result['analysis']['load_cases']), 'combinations': len(result['analysis']['combinations']), 'zip_path': result['zip_path'], 'artifacts': result['artifacts']}, ensure_ascii=False, indent=2)); return 0
if __name__ == '__main__': raise SystemExit(main())