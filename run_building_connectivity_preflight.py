from __future__ import annotations
import argparse,hashlib,json,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import ezdxf
from pypdf import PdfReader
from run_multistorey_stack_demo import build_demo as build_stack_demo
from structural_engine.building_model_preflight import audit_building_candidate_connectivity,create_connectivity_review_package,render_connectivity_dxf,render_connectivity_report_pdf

def run(out_dir:Path)->dict:
 out_dir.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix="structural_connectivity_source_") as td:
  source_dir=Path(td)/"source_stack";build_stack_demo(source_dir);model=json.loads((source_dir/"building_stack_candidate.json").read_text(encoding="utf-8"))
 result=audit_building_candidate_connectivity(model)
 (out_dir/"building_stack_candidate.json").write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding="utf-8")
 (out_dir/"building_connectivity_precheck.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 (out_dir/"building_connectivity_precheck.dxf").write_bytes(render_connectivity_dxf(model,result));render_connectivity_report_pdf(result,out_dir/"building_connectivity_precheck.pdf")
 package=create_connectivity_review_package(model,result);(out_dir/"building_connectivity_precheck_package.zip").write_bytes(package)
 pages=len(PdfReader(str(out_dir/"building_connectivity_precheck.pdf")).pages);dxf=ezdxf.readfile(out_dir/"building_connectivity_precheck.dxf")
 if pages<1 or len(dxf.modelspace())<10:raise RuntimeError("Connectivity outputs failed basic PDF/DXF re-open checks.")
 manifest={}
 for p in sorted(out_dir.iterdir()):
  if p.is_file() and p.name!="manifest_sha256.json":manifest[p.name]={"size_bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
 (out_dir/"manifest_sha256.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
 archive=out_dir.with_suffix(".zip")
 with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as z:
  for p in sorted(out_dir.iterdir()):
   if p.is_file():z.write(p,p.name)
 with zipfile.ZipFile(archive) as z:
  if z.testzip():raise RuntimeError("Connectivity preflight ZIP failed integrity check.")
  for name,item in manifest.items():
   if hashlib.sha256(z.read(name)).hexdigest()!=item["sha256"]:raise RuntimeError(f"Hash mismatch in outer package: {name}")
 return {"status":result["status"],"output_dir":str(out_dir),"archive":str(archive),"counts":result["counts"],"analysis_ready":result["analysis_gate"]["analysis_ready"],"blocker_codes":sorted({x["code"] for x in result["issues"] if x["severity"]=="BLOCKER"}),"pdf_pages":pages,"dxf_entities":len(dxf.modelspace()),"release":"NOT_FOR_CONSTRUCTION"}

def main()->int:
 parser=argparse.ArgumentParser();parser.add_argument("--out",default=str(ROOT/"output"/"building_connectivity_preflight_v0_14_0"));args=parser.parse_args();result=run(Path(args.out).resolve());print(json.dumps(result,ensure_ascii=False,indent=2))
 if result["analysis_ready"]:raise RuntimeError("Safety gate failed: preflight must never mark model analysis-ready.")
 return 0
if __name__=="__main__":raise SystemExit(main())