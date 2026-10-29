"""Bounded local Ollama tool-calling agent for review-only engineering workflows."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any,Callable
import json,time
@dataclass
class EngineeringTool:
 name:str
 description:str
 parameters:dict[str,Any]
 handler:Callable[[dict[str,Any]],dict[str,Any]]
 def schema(self):return {"type":"function","function":{"name":self.name,"description":self.description,"parameters":self.parameters}}
 def execute(self,args):
  if not isinstance(args,dict):raise ValueError("Tool args must be an object.")
  return self.handler(args)
@dataclass
class AgentResult:
 final_text:str
 stopped_reason:str
 trace:list[dict[str,Any]]
 tool_results:dict[str,Any]
def _safe(x):
 if isinstance(x,bytes):return {"type":"bytes","size":len(x)}
 if isinstance(x,dict):return {str(k):_safe(v) for k,v in x.items() if not str(k).startswith("_")}
 if isinstance(x,list):return [_safe(v) for v in x]
 if isinstance(x,(str,int,float,bool)) or x is None:return x
 return str(x)
def build_engineering_tools(state,runtime=None):
 runtime=runtime if runtime is not None else {};runtime.setdefault("tool_results",{})
 def project(_):
  p=state.get("project_fields") or {};d=state.get("dxf_summary") or {};g=[]
  for k,l in [("project_name","اسم المشروع"),("location","الموقع"),("building_use","الاستخدام"),("code_reference_as_entered","مرجع الكود"),("soil_report_status","تقرير التربة"),("live_load_source_as_entered","مصدر الحمل الحي"),("lateral_load_basis_as_entered","الأحمال الجانبية")]:
   if not p.get(k):g.append(l)
  if not d:g.append("رفع مسقط DXF")
  if not state.get("dxf_units_confirmed"):g.append("تأكيد الوحدة")
  if not state.get("dxf_review_confirmed"):g.append("مراجعة المسقط")
  if not state.get("building_stack_model"):g.append("تكوين الأدوار والمناسيب")
  return {"tool_status":"OK","project_name":p.get("project_name"),"location":p.get("location"),"dxf_entities":d.get("modelspace_entity_count"),"critical_gaps":g,"gap_count":len(g),"automatic_analysis_allowed":False}
 def dxf(_):
  a=state.get("dxf_structural_analysis") or {};s=state.get("dxf_summary") or {}
  if not a and not s:return {"tool_status":"BLOCKED","reason":"No DXF in workspace","required_user_action":"ارفع مسقط DXF أولًا."}
  return {"tool_status":"OK","filename":s.get("filename") or state.get("source_dxf_name"),"entity_count":s.get("modelspace_entity_count"),"layers":s.get("layers",[])[:35],"extents":s.get("extents") or a.get("extents_raw"),"architectural_intake":a.get("architectural_intake"),"warnings":a.get("warnings",[]),"automatic_analysis_allowed":False}
 def building(_):
  m=state.get("building_stack_model") or {}
  if not m:return {"tool_status":"BLOCKED","reason":"No building candidate"}
  return {"tool_status":"OK","status":m.get("status"),"counts":m.get("counts"),"levels":[{k:x.get(k) for k in ("floor_id","label_ar","kind","elevation_m","source_filename","proxy_plan")} for x in m.get("plan_instances",[])],"critical_missing_inputs":m.get("critical_missing_inputs",[])[:20],"warnings":m.get("warnings",[])[:15],"analysis_gate":m.get("review_gate")}
 def preflight(_):
  m=state.get("building_stack_model")
  if not m:return {"tool_status":"BLOCKED","reason":"No building candidate"}
  from .building_model_preflight import audit_building_candidate_connectivity
  r=audit_building_candidate_connectivity(m);runtime["preflight_result"]=r
  return {"tool_status":r.get("status"),"counts":r.get("counts"),"critical_model_gaps":r.get("critical_model_gaps",[])[:8],"blockers":[x for x in r.get("issues",[]) if x.get("severity")=="BLOCKER"][:15],"analysis_gate":r.get("analysis_gate")}
 def infer(_):
  a=state.get("dxf_structural_analysis") or {}
  if not a:return {"tool_status":"BLOCKED","reason":"No structured DXF"}
  from .dxf_structural_inference import build_dxf_candidate_model
  decisions=state.get("dxf_review_rows") or [{"entity_id":str(e["entity_id"]),"review_role":e.get("suggested_role","unknown"),"included":bool(e.get("included",False)),"reviewed":False} for e in a.get("entities",[])]
  c=build_dxf_candidate_model(a,decisions,metres_per_drawing_unit=float(state.get("dxf_metres_per_unit") or .001),units_confirmed=bool(state.get("dxf_units_confirmed")),layer_dimensions_confirmed=bool(state.get("dxf_layer_dimensions_confirmed")),project_fields=state.get("project_fields") or {})
  runtime["dxf_candidate_model"]=c
  return {"tool_status":"DRAFT_CREATED","candidate_status":c.get("candidate_status"),"candidate_counts":c.get("component_counts"),"candidate_review_basis":"individual_review" if state.get("dxf_review_rows") else "layer_hints_only","missing_inputs":c.get("structural_proposal",{}).get("missing_inputs",[]),"automatic_analysis_allowed":False}
 def propose(_):
  r=infer({});c=runtime.get("dxf_candidate_model") or {}
  c.setdefault("structural_proposal",{})["system_candidates"]=[{"system_id":"rc_beam_slab","name_ar":"بلاطات وكمرات"},{"system_id":"rc_flat_plate","name_ar":"بلاطة مسطحة"},{"system_id":"rc_shear_wall","name_ar":"حوائط قص/نظام مزدوج"}];c["structural_proposal"]["automatic_analysis_allowed"]=False
  runtime["dxf_candidate_model"]=c
  return {"tool_status":"DRAFT_CREATED","candidate_status":c.get("candidate_status"),"candidate_counts":c.get("component_counts"),"rationale":"ترشيح أولي من بيانات الطبقات فقط؛ يلزم فحص البحور والاتصال والأحمال والانتظام.","alternatives":c["structural_proposal"]["system_candidates"],"entity_roles_individually_reviewed":bool(state.get("dxf_review_rows")),"missing_inputs":c["structural_proposal"].get("missing_inputs",[]),"automatic_analysis_allowed":False}
 def recommend(_):
  c=runtime.get("dxf_candidate_model") or {};p=c.setdefault("structural_proposal",{});rec={"system_id":"insufficient_data","name_ar":"البيانات غير كافية لاختيار نظام","status":"NEEDS_ENGINEER_INPUT","rationale":"أسماء الطبقات لا تثبت البحور أو نظام البلاطات أو الاتصال أو المقاومة الجانبية.","alternatives":p.get("system_candidates",[]),"based_on_observations":[{"layer":x.get("layer"),"role_candidate":x.get("suggested_role")} for x in (state.get("dxf_structural_analysis") or {}).get("entities",[])[:20]],"missing_inputs":["البحور والقيود المعمارية","نوع البلاطات والفتحات","الأحمال والارتفاعات","الموقع والرياح والزلازل","تقرير التربة","اتصالات العناصر"]}
  p["ai_system_recommendation"]=rec;runtime["dxf_candidate_model"]=c
  return {"tool_status":"RECOMMENDATION_DRAFT",**rec,"automatic_analysis_allowed":False}
 schema={"type":"object","properties":{},"additionalProperties":False}
 defs=[("inspect_project_status","Inspect confirmed project fields and missing prerequisites.",project),("inspect_uploaded_dxf","Read current DXF geometry and layer metadata.",dxf),("inspect_multistorey_building_context","Inspect storey levels, plan sources and vertical continuity.",building),("preflight_building_model_connectivity","Audit candidate geometry; this never approves analysis.",preflight),("infer_dxf_structural_geometry","Create review-only geometry candidates from reviewed DXF roles.",infer),("list_structural_system_options","List candidate systems and required inputs.",lambda _ :{"tool_status":"OK","systems":[{"system_id":"rc_beam_slab","name_ar":"بلاطات وكمرات"},{"system_id":"rc_flat_plate","name_ar":"بلاطة مسطحة"},{"system_id":"rc_shear_wall","name_ar":"حوائط قص/نظام مزدوج"},{"system_id":"load_bearing_walls","name_ar":"حوائط حاملة"}],"automatic_analysis_allowed":False}),("propose_structural_scheme_from_reviewed_dxf","Create a draft candidate from reviewed DXF information.",propose),("recommend_structural_system_from_reviewed_dxf","Record an AI recommendation or insufficient-data decision with reasons.",recommend)]
 return [EngineeringTool(n,d,schema,h) for n,d,h in defs]
class EngineeringAgent:
 def __init__(self,client=None,max_tool_calls=6,max_model_rounds=7):
  if client is None:
   from .ai_copilot import OllamaClient
   client=OllamaClient()
  self.client=client;self.max_tool_calls=max(1,min(int(max_tool_calls),10));self.max_model_rounds=max(1,min(int(max_model_rounds),10))
 def run(self,model,messages,tools,*,image_bytes=None):
  definitions=[x.schema() for x in tools];byname={x.name:x for x in tools};chat=[dict(x) for x in messages];trace=[];results={};seen=set();count=0;reason="MAX_ROUNDS"
  for rnd in range(1,self.max_model_rounds+1):
   data=self.client.chat_response(model,chat,image_bytes=image_bytes if rnd==1 else None,tools=definitions,options={"temperature":.1,"num_ctx":4096,"num_predict":700});msg=data.get("message",{});calls=msg.get("tool_calls") or [];content=str(msg.get("content") or "").strip()
   if not calls:return AgentResult(content or "لم يرجع النموذج إجابة نصية.", "MODEL_FINAL_RESPONSE",trace,results)
   chat.append({"role":"assistant","content":content,"tool_calls":calls})
   for call in calls:
    fn=call.get("function") or {};name=str(fn.get("name") or "");args=fn.get("arguments") or {}
    if isinstance(args,str):
     try:args=json.loads(args)
     except Exception:args={}
    start=time.perf_counter()
    if name not in byname:res={"status":"BLOCKED","error":"Unknown tool"};status="BLOCKED"
    elif name in seen:res={"status":"BLOCKED","error":"Repeated tool blocked to prevent loop"};status="BLOCKED"
    elif count>=self.max_tool_calls:res={"status":"BLOCKED","error":"Tool-call budget reached"};status="BLOCKED"
    else:
     seen.add(name);count+=1
     try:res=byname[name].execute(args);status=str(res.get("tool_status",res.get("status","OK")))
     except Exception as e:res={"status":"ERROR","error":str(e)};status="ERROR"
     results[name]=res
    trace.append({"round":rnd,"tool":name,"status":status,"duration_seconds":round(time.perf_counter()-start,4),"result":_safe(res)})
    chat.append({"role":"tool","tool_name":name or "unknown","content":json.dumps(_safe(res),ensure_ascii=False,default=str)[:9000]})
   image_bytes=None
  reason="MAX_TOOL_CALLS" if count>=self.max_tool_calls else "MAX_ROUNDS"
  try:data=self.client.chat_response(model,chat,options={"temperature":.1,"num_ctx":4096,"num_predict":700});final=str((data.get("message") or {}).get("content") or "").strip()
  except Exception as e:final=f"انتهت خطوات الوكيل؛ راجع سجل الأدوات. {e}"
  return AgentResult(final or "انتهت خطوات الوكيل؛ راجع الموانع قبل القرار الهندسي.",reason,trace,results)
