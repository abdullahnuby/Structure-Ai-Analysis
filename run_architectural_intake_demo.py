from __future__ import annotations
import argparse,csv,hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from structural_engine.dxf_preview import render_dxf_preview_png
from structural_engine.dxf_structural_inference import analyze_dxf_structure,build_dxf_candidate_model,create_candidate_review_package,render_candidate_overlay_png,validate_architectural_layer_geometry

def build_demo(out_dir:Path)->dict:
 source=ROOT/"examples"/"architectural_standard_demo.dxf"
 if not source.exists(): raise FileNotFoundError(f"ملف المثال غير موجود: {source}")
 raw=source.read_bytes(); analysis=analyze_dxf_structure(raw,source.name)
 decisions=[{"entity_id":str(e["entity_id"]),"review_role":str(e.get("suggested_role","unknown")),"included":bool(e.get("included",False)),"reviewed":True,"suggested_role":e.get("suggested_role"),"entity_type":e.get("entity_type"),"layer":e.get("layer"),"confidence":e.get("confidence"),"evidence":e.get("evidence")} for e in analysis.get("entities",[])]
 scale=float(analysis.get("suggested_metres_per_unit") or 0.001)
 geometry=validate_architectural_layer_geometry(analysis,metres_per_drawing_unit=scale,units_confirmed=True,layer_dimensions_confirmed=True)
 candidate=build_dxf_candidate_model(analysis,decisions,metres_per_drawing_unit=scale,units_confirmed=True,layer_dimensions_confirmed=True,project_fields={"project_name":"DEMO — architectural intake only","code_reference_as_entered":"not selected"})
 preview=render_dxf_preview_png(raw,source.name); overlay=render_candidate_overlay_png(preview,analysis,decisions); package=create_candidate_review_package(analysis,candidate,decisions,overlay)
 out_dir.mkdir(parents=True,exist_ok=True)
 files={"source_architectural_plan.dxf":raw,"dxf_geometry_analysis.json":json.dumps(analysis,ensure_ascii=False,indent=2).encode(),"candidate_structural_floor.json":json.dumps(candidate,ensure_ascii=False,indent=2).encode(),"column_layer_geometry_check.json":json.dumps(geometry,ensure_ascii=False,indent=2).encode(),"source_preview.png":preview,"candidate_overlay.png":overlay,"candidate_review_package.zip":package,"README_AR.md":"# تجربة إدخال DXF معماري\n\nبيانات اختبار مصطنعة لبناء نموذج مرشح للمراجعة فقط. لا يوجد تحليل أو تصميم أو تسليح؛ المخرجات NOT FOR CONSTRUCTION.\n".encode()}
 import io
 buff=io.StringIO(newline=""); fields=["entity_id","entity_type","layer","suggested_role","review_role","included","confidence","evidence"]; writer=csv.DictWriter(buff,fieldnames=fields,extrasaction="ignore");writer.writeheader();writer.writerows(decisions);files["entity_review.csv"]=buff.getvalue().encode("utf-8-sig")
 manifest={n:{"size_bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()} for n,b in sorted(files.items())}; files["manifest_sha256.json"]=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
 for name,data in files.items():(out_dir/name).write_bytes(data)
 zpath=out_dir/"architectural_intake_demo_v0_12_0.zip"
 with zipfile.ZipFile(zpath,"w",zipfile.ZIP_DEFLATED) as z:
  for name in sorted(files):z.write(out_dir/name,arcname=name)
 with zipfile.ZipFile(zpath) as z:
  bad=z.testzip()
  if bad:raise RuntimeError(f"فشل فحص ZIP عند {bad}")
 return {"source":str(source),"out_dir":str(out_dir),"zip":str(zpath),"entities":len(analysis.get("entities",[])),"layers":len(analysis.get("layers",[])),"candidate_counts":candidate.get("component_counts",{}),"title_candidates":analysis.get("architectural_intake",{}).get("plan_title_candidates",[]),"column_geometry_check":geometry.get("status"),"column_geometry_checked":geometry.get("checked_columns",0),"column_geometry_mismatches":geometry.get("mismatches",0),"candidate_status":candidate.get("candidate_status"),"analysis_allowed":candidate.get("review",{}).get("automatic_analysis_allowed",False)}

def main()->int:
 parser=argparse.ArgumentParser(description="Build a review-only architectural DXF intake demo package.");parser.add_argument("--out",default=str(ROOT/"output"/"architectural_intake_demo"));args=parser.parse_args(); result=build_demo(Path(args.out).resolve());print(json.dumps(result,ensure_ascii=False,indent=2))
 if result["analysis_allowed"]:return 2
 if result["candidate_status"]!="DRAFT_NEEDS_ENGINEER_REVIEW_NOT_FOR_CONSTRUCTION":return 3
 return 0
if __name__=="__main__":raise SystemExit(main())