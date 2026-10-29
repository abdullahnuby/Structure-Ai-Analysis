"""Conservative layer-led DXF interpretation and review package."""
from __future__ import annotations
from collections import Counter
from io import BytesIO,StringIO
from pathlib import Path
from tempfile import NamedTemporaryFile
import csv,hashlib,json,math,re,zipfile,ezdxf
from PIL import Image,ImageDraw,ImageFont
from .dxf_preview import render_dxf_preview_png
PAIR=re.compile(r"(\d+(?:[.,]\d+)?)\s*(mm|cm|ملم|سم)?\s*(?:\*|x|×)\s*(\d+(?:[.,]\d+)?)\s*(mm|cm|ملم|سم)?",re.I)
SINGLE=re.compile(r"(\d+(?:[.,]\d+)?)\s*(mm|cm|ملم|سم)",re.I)
HEAD=re.compile(r"^\s*(column|columns|col|beam|girder|wall|walls|partition|slab|floor|plate|opening|door|window|text|grid|axis|عمود|اعمدة|أعمدة|كمرة|كمر|حائط|حوائط|جدار|بلاطة|سقف|فتحة|باب|شباك|محور|نص)(?:\s|$)",re.I)
def parse_architectural_layer(name):
 raw=str(name or "").strip();norm=re.sub(r"\s+"," ",re.sub(r"[_\-.]+"," ",raw)).strip().casefold();m=HEAD.match(norm);tok=m.group(1).casefold() if m else ""
 role=("column" if tok in {"column","columns","col","عمود","اعمدة","أعمدة"} else "beam" if tok in {"beam","girder","كمرة","كمر"} else "wall" if tok in {"wall","walls","partition","حائط","حوائط","جدار"} else "slab" if tok in {"slab","floor","plate","بلاطة","سقف"} else "opening" if tok in {"opening","door","window","فتحة","باب","شباك"} else "text" if tok=="text" or norm=="text" or tok=="نص" else "grid_axis" if tok in {"grid","axis","عمور","محور"} else "unknown")
 out={"layer_name":raw,"parsed_role":role,"dimensions_cm":None,"dimension_parse_status":"NOT_APPLICABLE","is_title_layer":role=="text"}
 if role in {"column","beam"}:
  z=PAIR.search(norm)
  if z:
   a,b=float(z.group(1).replace(",",".")),float(z.group(3).replace(",","."))
   if any((u or "").casefold() in {"mm","ملم"} for u in [z.group(2),z.group(4)]):a,b=a/10,b/10
   out.update(dimensions_cm={"width":a,"depth":b},dimension_parse_status="PARSED_NEEDS_CONFIRMATION")
  else:out["dimension_parse_status"]="MISSING_SECTION_PAIR"
 if role in {"wall","slab"}:
  z=SINGLE.search(norm)
  if z:
   v=float(z.group(1).replace(",","."));u=(z.group(2) or "").casefold()
   if u in {"mm","ملم"}:v/=10
   out.update(dimensions_cm={"thickness":v},dimension_parse_status="PARSED_NEEDS_CONFIRMATION")
 return out
def _pts(e):
 k=e.dxftype()
 try:
  if k=="LINE":return [[float(e.dxf.start.x),float(e.dxf.start.y)],[float(e.dxf.end.x),float(e.dxf.end.y)]]
  if k=="LWPOLYLINE":return [[float(p[0]),float(p[1])] for p in e.get_points("xy")]
  if k=="POLYLINE":return [[float(v.dxf.location.x),float(v.dxf.location.y)] for v in e.vertices]
  if k in {"TEXT","MTEXT","ATTRIB","ATTDEF"}:return [[float(e.dxf.insert.x),float(e.dxf.insert.y)]]
  if k=="POINT":return [[float(e.dxf.location.x),float(e.dxf.location.y)]]
 except Exception:return []
 return []
def _text(e):
 try:return str(e.plain_text() if e.dxftype()=="MTEXT" else e.dxf.get("text","")).strip()
 except Exception:return ""
def analyze_dxf_structure(data:bytes,filename="drawing.dxf"):
 if not data:raise ValueError("DXF file is empty.")
 with NamedTemporaryFile(suffix=".dxf",delete=False) as f:f.write(data);p=Path(f.name)
 try:doc=ezdxf.readfile(p)
 except Exception as e:raise ValueError(f"Invalid DXF: {e}") from e
 finally:p.unlink(missing_ok=True)
 es=[];types=Counter();layers=Counter();allp=[]
 for i,e in enumerate(doc.modelspace(),1):
  k=e.dxftype();ln=str(e.dxf.get("layer","0"));pts=_pts(e);allp.extend(pts);spec=parse_architectural_layer(ln);box={"min_x":min(x[0] for x in pts),"max_x":max(x[0] for x in pts),"min_y":min(x[1] for x in pts),"max_y":max(x[1] for x in pts)} if pts else None;role={"slab":"slab_outline","text":"annotation"}.get(spec["parsed_role"],spec["parsed_role"])
  if role=="unknown" and k in {"TEXT","MTEXT","DIMENSION","LEADER"}:role="annotation"
  es.append({"entity_id":f"E{i:05d}","entity_type":k,"layer":ln,"text":_text(e)[:400],"points_raw":pts,"bbox_raw":box,"geometry_raw":{"points":pts,"bbox":box,"closed":bool(getattr(e,"closed",False) or getattr(e,"is_closed",False))},"layer_spec":spec,"suggested_role":role,"included":role not in {"unknown","annotation"},"confidence":.95 if spec["parsed_role"]!="unknown" else .15,"evidence":[f"layer:{ln}",f"entity:{k}"]});types[k]+=1;layers[ln]+=1
 ext={"min_x":min(p[0] for p in allp),"max_x":max(p[0] for p in allp),"min_y":min(p[1] for p in allp),"max_y":max(p[1] for p in allp)} if allp else None;titles=[{"text":e["text"],"entity_id":e["entity_id"]} for e in es if e["layer_spec"]["is_title_layer"] and e["text"]];hints=[{"layer":x,"role":parse_architectural_layer(x)["parsed_role"],"dimensions_cm":parse_architectural_layer(x)["dimensions_cm"]} for x in sorted(layers) if parse_architectural_layer(x)["parsed_role"]!="unknown"]
 return {"filename":Path(filename).name,"dxf_version":doc.dxfversion,"insunits_code":int(doc.header.get("$INSUNITS",0) or 0),"modelspace_entity_count":len(es),"entity_counts":dict(types),"layers":[{"name":x,"entity_count":layers[x]} for x in sorted(layers)],"extents_raw":ext,"entities":es,"architectural_intake":{"plan_title_candidates":titles,"layer_role_hints":hints,"system_hypotheses":[{"system":"rc_beam_slab","status":"NOT_ASSESSED"},{"system":"rc_flat_plate","status":"NOT_ASSESSED"}]},"warnings":["طبقات الرسم مؤشرات وليست إثباتًا للوظيفة الإنشائية.","يجب تأكيد الوحدة والبعد والمحاور يدويًا.","عدم وجود كمرة مرسومة لا يثبت صلاحية البلاطة المسطحة."]}
def validate_architectural_layer_geometry(analysis,*,metres_per_drawing_unit,units_confirmed,layer_dimensions_confirmed,tolerance_m=.03):
 if not units_confirmed or not layer_dimensions_confirmed:return {"status":"BLOCKED_CONFIRM_UNITS_AND_LAYER_DIMENSIONS","checked_columns":0,"mismatches":0,"records":[]}
 s=float(metres_per_drawing_unit)
 if not math.isfinite(s) or s<=0:raise ValueError("Scale must be positive.")
 rows=[];mis=0
 for e in analysis.get("entities",[]):
  sp=e.get("layer_spec") or {};b=e.get("bbox_raw");d=sp.get("dimensions_cm")
  if sp.get("parsed_role")!="column" or not b or not d:continue
  a=sorted([(b["max_x"]-b["min_x"])*s,(b["max_y"]-b["min_y"])*s]);q=sorted([float(d["width"])/100,float(d["depth"])/100]);delta=max(abs(a[i]-q[i]) for i in (0,1));ok=delta<=tolerance_m;mis+=not ok;rows.append({"entity_id":e["entity_id"],"layer":e["layer"],"drawn_dim_a_m":a[0],"drawn_dim_b_m":a[1],"declared_dim_a_m":q[0],"declared_dim_b_m":q[1],"max_abs_delta_m":delta,"status":"MATCH" if ok else "MISMATCH_REVIEW"})
 return {"status":"PASS" if not mis else "MISMATCH_REVIEW","checked_columns":len(rows),"mismatches":mis,"tolerance_m":tolerance_m,"records":rows}
def build_dxf_candidate_model(analysis,decisions,*,metres_per_drawing_unit,units_confirmed,layer_dimensions_confirmed,project_fields=None):
 if not units_confirmed:raise ValueError("Confirm drawing units.")
 scale=float(metres_per_drawing_unit)
 if scale<=0 or not math.isfinite(scale):raise ValueError("Invalid scale.")
 dm={str(d.get("entity_id")):d for d in decisions};comps=[];counts=Counter()
 for e in analysis.get("entities",[]):
  d=dm.get(str(e["entity_id"]),{});role=d.get("review_role",e.get("suggested_role","unknown"))
  if not d.get("included",e.get("included",False)) or role in {"unknown","ignore","annotation"}:continue
  pts=[[float(p[0])*scale,float(p[1])*scale] for p in (e.get("points_raw") or [])];b=e.get("bbox_raw");box={k:float(v)*scale for k,v in b.items()} if b else None;spec=e.get("layer_spec") or {};dims=spec.get("dimensions_cm")
  c={"candidate_id":f"C-{e['entity_id']}","source_entity_id":e["entity_id"],"role":role,"source_layer":e.get("layer"),"entity_type":e.get("entity_type"),"confidence":e.get("confidence",.2),"evidence":e.get("evidence",[]),"geometry_raw":e.get("geometry_raw"),"geometry_m":{"points":pts,"bbox":box,"closed":bool((e.get("geometry_raw") or {}).get("closed",False))},"declared_dimensions_cm":dims,"section_cm_as_drawn":dims if role in {"column","beam"} else None,"design_status":"NOT_DESIGNED","review_status":"DRAFT"}
  if role=="column" and box:c["center_3d_m"]=[(box["min_x"]+box["max_x"])/2,(box["min_y"]+box["max_y"])/2,0.]
  comps.append(c);counts[role]+=1
 return {"schema_version":"dxf_structural_candidate/0.18.0","candidate_status":"DRAFT_NEEDS_ENGINEER_REVIEW_NOT_FOR_CONSTRUCTION","source_dxf":{"filename":analysis.get("filename"),"dxf_version":analysis.get("dxf_version"),"units_confirmed":True,"metres_per_drawing_unit":scale},"project_context":project_fields or {},"architectural_intake":analysis.get("architectural_intake"),"components":comps,"component_counts":dict(counts),"plan_warnings":[],"geometry_to_layer_size_check":validate_architectural_layer_geometry(analysis,metres_per_drawing_unit=scale,units_confirmed=True,layer_dimensions_confirmed=layer_dimensions_confirmed),"layer_contract":{"standard_confirmed_by_user":layer_dimensions_confirmed,"entity_geometry_individually_reviewed":bool(decisions) and all(d.get("reviewed",False) for d in decisions),"unmapped_layers":[x["name"] for x in analysis.get("layers",[]) if (parse_architectural_layer(x["name"]) or {}).get("parsed_role")=="unknown"]},"structural_proposal":{"status":"DRAFT_NOT_ANALYSIS_READY","missing_inputs":["اتصالات العناصر والبحور","نوع وسُمك البلاطات","الأحمال والمواد","الأدوار والمناسيب","التربة والرياح والزلازل","مرجع الكود"],"automatic_analysis_allowed":False},"review":{"automatic_analysis_allowed":False},"warnings":["المكونات مرشحة وغير معتمدة؛ لا يوجد تصميم أو تسليح."]}
def render_candidate_overlay_png(base_preview,analysis,decisions=None,*,width=1280,height=900):
 img=Image.open(BytesIO(base_preview)).convert("RGB");d=ImageDraw.Draw(img);f=ImageFont.load_default();by={e["entity_id"]:e for e in analysis.get("entities",[])};cols={"column":"#d33","beam":"#2876ae","wall":"#7652a8","slab_outline":"#187d62","grid_axis":"#d88820"}
 for row in decisions or []:
  e=by.get(str(row.get("entity_id")));b=(e or {}).get("bbox_raw")
  if not b:continue
  ex=analysis.get("extents_raw") or {}
  try:
   mnx,mny,mxx,mxy=[float(ex[k]) for k in ("min_x","min_y","max_x","max_y")];x=(b["min_x"]+b["max_x"])/2;y=(b["min_y"]+b["max_y"])/2;s=min((img.width-70)/max(mxx-mnx,1e-6),(img.height-70)/max(mxy-mny,1e-6));px=int(35+(x-mnx)*s);py=int(35+(mxy-y)*s);role=row.get("review_role",e.get("suggested_role","unknown"));color=cols.get(role,"#333");r=5 if row.get("included") else 3;d.ellipse((px-r,py-r,px+r,py+r),fill=color);d.text((px+6,py-6),role[:4],fill=color,font=f)
  except Exception:pass
 o=BytesIO();img.save(o,format="PNG");return o.getvalue()
def create_candidate_review_package(analysis,candidate,decisions,overlay_png)->bytes:
 files={"geometry_analysis.json":json.dumps(analysis,ensure_ascii=False,indent=2).encode(),"candidate_model.json":json.dumps(candidate,ensure_ascii=False,indent=2).encode(),"candidate_overlay.png":overlay_png};out=StringIO(newline="");fields=["entity_id","entity_type","layer","suggested_role","review_role","included","confidence","reviewed"];w=csv.DictWriter(out,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(decisions);files["entity_review.csv"]=out.getvalue().encode("utf-8-sig");files["manifest_sha256.json"]=json.dumps({n:hashlib.sha256(b).hexdigest() for n,b in sorted(files.items())},indent=2).encode();z=BytesIO()
 with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as f:
  for n,b in files.items():f.writestr(n,b)
 with zipfile.ZipFile(BytesIO(z.getvalue())) as f:
  if f.testzip():raise ValueError("Candidate ZIP integrity error.")
 return z.getvalue()
