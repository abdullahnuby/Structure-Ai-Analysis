from __future__ import annotations

import argparse, hashlib, json, shutil, sys, tempfile, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
import ezdxf
from structural_engine.building_stack import (build_multistorey_building_candidate, create_building_stack_review_package, make_architectural_plan_candidate, render_building_stack_preview_png)

def _translated_copy(source: Path, destination: Path, dx: float, dy: float) -> bytes:
    doc = ezdxf.readfile(source)
    for entity in list(doc.modelspace()):
        try: entity.translate(dx, dy, 0)
        except Exception: pass
    doc.saveas(destination); return destination.read_bytes()

def build_demo(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True); source = ROOT / "examples" / "architectural_standard_demo.dxf"; ground_raw = source.read_bytes()
    with tempfile.TemporaryDirectory(prefix="stack_demo_") as td:
        shifted_path = Path(td) / "typical_floor_shifted.dxf"; typical_raw = _translated_copy(source, shifted_path, 25000, -14000); basement_raw = ground_raw
        ground = make_architectural_plan_candidate(ground_raw, "ground_floor.dxf", metres_per_drawing_unit=.001, units_confirmed=True, layer_conventions_confirmed=True, floor_identity="ground", project_fields={"project_name":"DEMO MULTI-STOREY", "location":"Test only"})
        typical = make_architectural_plan_candidate(typical_raw, "typical_floor.dxf", metres_per_drawing_unit=.001, units_confirmed=True, layer_conventions_confirmed=True, floor_identity="typical", project_fields={"project_name":"DEMO MULTI-STOREY", "location":"Test only"})
        basement = make_architectural_plan_candidate(basement_raw, "basement_proxy_fixture.dxf", metres_per_drawing_unit=.001, units_confirmed=True, layer_conventions_confirmed=True, floor_identity="basement", project_fields={"project_name":"DEMO MULTI-STOREY", "location":"Test only"})
        cfg = {"project_name":"DEMO MULTI-STOREY — NOT FOR CONSTRUCTION", "location":"Luxor, Egypt (fixture)", "building_use":"residential (demo)", "code_reference":"ECP203-2025 entered by user; not verified", "concrete_strength_mpa":30, "steel_yield_strength_mpa":420, "above_ground_story_count":4, "ground_story_height_m":4.2, "upper_story_height_mode":"individual", "upper_story_heights_m":[3.2,3.0,3.5], "typical_story_height_m":3.2, "ground_finished_floor_offset_from_street_m":0.45, "street_datum_elevation_m":0.0, "ground_plan_units_confirmed":True, "layer_conventions_confirmed":True, "typical_plan_mode":"separate", "basement_enabled":True, "basement_count":1, "basement_height_mode":"uniform", "basement_story_height_m":3.3,"basement_story_heights_m":[3.3], "basement_plan_mode":"separate", "roof_plan_mode":"typical_proxy", "foundation_system_candidate":"not_selected", "foundation_depth_below_lowest_floor_m":None, "soil_report_status":"not_available", "geotechnical_notes":"No geotechnical data — test fixture only", "groundwater_level_m_relative_to_street":None,"occupancy_load_basis":"Not supplied in fixture", "wind_basis":"Not supplied in fixture", "seismic_basis":"Not supplied in fixture", "site_class":"unknown", "plan_irregularities":"not assessed", "vertical_irregularities":"not assessed", "diaphragm_assumption":"not confirmed"}
        stack = build_multistorey_building_candidate(cfg, ground_plan=ground, typical_plan=typical, basement_plan=basement); preview = render_building_stack_preview_png(stack)
        package = create_building_stack_review_package(stack, preview, {"ground_floor.dxf":ground_raw, "typical_floor_shifted.dxf":typical_raw,"basement_fixture.dxf":basement_raw})
    (out_dir / "building_stack_candidate.json").write_text(json.dumps(stack, ensure_ascii=False, indent=2), encoding="utf-8"); (out_dir / "building_stack_preview.png").write_bytes(preview); (out_dir / "building_stack_review_package.zip").write_bytes(package)
    (out_dir / "README_AR.md").write_text("# تجربة تكديس مبنى متعدد الأدوار\n\nمثال اصطناعي: أرضي + 3 متكرر، اختلاف ارتفاعات، منسوب التشطيب بالنسبة للشارع، بدروم ومرجع سطح.\nالناتج ليس نموذج تحليل معتمدًا؛ كل القطاعات والحوائط والاتصالات والأحمال والأساسات تحتاج مراجعة.\n", encoding="utf-8")
    manifest = {p.name:{"size_bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out_dir.iterdir()) if p.is_file() and p.name!="manifest_sha256.json"}
    (out_dir / "manifest_sha256.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8"); archive=out_dir.with_suffix(".zip")
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(out_dir.iterdir()):
            if p.is_file(): zf.write(p,p.name)
    with zipfile.ZipFile(archive) as zf:
        if zf.testzip(): raise RuntimeError("ZIP validation failed")
    return {"output_dir":str(out_dir),"archive":str(archive),"above_ground_floors":stack["counts"]["above_ground_occupied_floor_plans"],"typical_instances":stack["counts"]["repeated_typical_plan_instances"],"basement_levels":stack["counts"]["basement_levels"],"plan_levels":stack["counts"]["plan_levels_including_basement_and_roof"],"column_segments":stack["counts"]["column_segments"],"continuity_pairs":len(stack["vertical_continuity_checks"]),"analysis_ready":stack["review_gate"]["analysis_ready"],"roof_elevation_m":stack["vertical_3d_extents"]["roof_level_m"],"warnings":len(stack["warnings"])}

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--out",default=str(ROOT/"output"/"building_stack_demo_v0_13_0")); args=parser.parse_args(); result=build_demo(Path(args.out).resolve()); print(json.dumps(result,ensure_ascii=False,indent=2))
    if result["analysis_ready"]: return 2
    if result["above_ground_floors"] != 4 or result["typical_instances"] != 3: return 3
    return 0
if __name__=="__main__": raise SystemExit(main())