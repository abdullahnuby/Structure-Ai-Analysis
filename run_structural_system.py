from __future__ import annotations
import argparse, csv, hashlib, io, json
from pathlib import Path
import zipfile
from structural_engine.structural_systems import assess_structural_system
RECORD_KEYS = ("column_loads", "slab_strip_results", "rib_loads", "wall_loads", "panels")
def _json_dump(path: Path, data: object) -> None: path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
def _csv_bytes(records: list[dict]) -> bytes:
    if not records: return b""
    fields=sorted({key for row in records for key in row}); buffer=io.StringIO(newline=""); writer=csv.DictWriter(buffer,fieldnames=fields,extrasaction="ignore"); writer.writeheader(); writer.writerows(records); return ("\ufeff"+buffer.getvalue()).encode("utf-8")
def run(model_path: Path, out_dir: Path) -> dict:
    config=json.loads(model_path.read_text(encoding="utf-8-sig"))
    if not isinstance(config,dict): raise ValueError("Input model must be a JSON object.")
    system_id=str(config.get("system_id","")).strip()
    if not system_id: raise ValueError("Input JSON must include system_id.")
    package=assess_structural_system(system_id,config); assessment=package["assessment"]; out_dir.mkdir(parents=True,exist_ok=True)
    for name in ("system_assessment.json","system_loads.csv","system_assessment_summary.md","SHA256SUMS.json","structural_system_package.zip"):
        old=out_dir/name
        if old.exists() and old.is_file(): old.unlink()
    result_path=out_dir/"system_assessment.json"; _json_dump(result_path,package)
    records=[]; record_type=None
    for key in RECORD_KEYS:
        candidate=assessment.get(key)
        if isinstance(candidate,list) and candidate: records,record_type=candidate,key; break
    csv_path=None
    if records: csv_path=out_dir/"system_loads.csv"; csv_path.write_bytes(_csv_bytes(records))
    qa=assessment.get("qa",{}); summary=[f"# Structural system assessment: {system_id}","",f"- Catalogue system: `{package['system']['name_ar']}`",f"- Result status: `{assessment.get('status','UNKNOWN')}`",f"- Code design status: `{package.get('code_design_status','NOT_IMPLEMENTED')}`",f"- Release: `{package.get('release','NOT_FOR_CONSTRUCTION')}`","","## Errors"]
    summary.extend([f"- {x}" for x in qa.get("errors",[])] or ["- None reported by this system gate."]); summary.extend(["","## Warnings and limits"]); summary.extend([f"- {x}" for x in qa.get("warnings",[])] or ["- No warnings returned."])
    summary.extend(["","## Output values","```json",json.dumps(assessment.get("totals",{}),ensure_ascii=False,indent=2),"```","","This output is a preliminary load-accounting/readiness artifact only. It is not a structural design, does not claim compliance with an Egyptian Code edition, and must not be used for construction."])
    (out_dir/"system_assessment_summary.md").write_text("\n".join(summary)+"\n",encoding="utf-8")
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out_dir.iterdir()) if p.is_file() and p.name!="SHA256SUMS.json"}; _json_dump(out_dir/"SHA256SUMS.json",manifest)
    zip_path=out_dir/"structural_system_package.zip"
    with zipfile.ZipFile(zip_path,"w",compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(out_dir.iterdir()):
            if path.is_file() and path.name!=zip_path.name: zf.write(path,arcname=path.name)
    with zipfile.ZipFile(zip_path) as zf:
        bad=zf.testzip()
        if bad: raise RuntimeError(f"ZIP integrity check failed at {bad}")
        for name in zf.namelist():
            if not zf.read(name) and name!="system_loads.csv": raise RuntimeError(f"Output artifact unexpectedly empty: {name}")
    if qa.get("errors"):
        print(f"INVALID_INPUT: {system_id}; {len(qa['errors'])} validation errors; artifacts written to {out_dir}"); return {"exit_code":2,"status":assessment.get("status"),"output_dir":str(out_dir),"system_id":system_id}
    print(f"PASS: {system_id}; status={assessment.get('status')}; outputs={out_dir}"); return {"exit_code":0,"status":assessment.get("status"),"output_dir":str(out_dir),"system_id":system_id,"csv_record_type":record_type,"csv_rows":len(records)}
def main() -> int:
    parser=argparse.ArgumentParser(description="Evaluate structural-system readiness or preliminary gravity accounting."); parser.add_argument("--model",required=True,type=Path,help="System configuration JSON file"); parser.add_argument("--out",required=True,type=Path,help="Output directory"); args=parser.parse_args()
    try: return int(run(args.model,args.out)["exit_code"])
    except Exception as exc: print(f"ERROR: {exc}"); return 1
if __name__ == "__main__": raise SystemExit(main())