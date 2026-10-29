"""Geometric multistorey candidate; never marks FE analysis ready."""

from __future__ import annotations
from collections import Counter
from io import BytesIO, StringIO
import csv, hashlib, json, math, zipfile
from PIL import Image, ImageDraw, ImageFont
from .dxf_structural_inference import analyze_dxf_structure, build_dxf_candidate_model
from .dxf_preview import render_dxf_preview_png


def make_architectural_plan_candidate(
    dxf_bytes,
    filename,
    *,
    metres_per_drawing_unit,
    units_confirmed,
    layer_conventions_confirmed,
    floor_identity,
    project_fields=None,
):
    if not units_confirmed or not layer_conventions_confirmed:
        raise ValueError("Confirm drawing units and layer naming standard first.")
    scale = float(metres_per_drawing_unit)
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("Invalid DXF unit scale.")
    if floor_identity not in {"ground", "typical", "basement", "roof"}:
        raise ValueError("Unknown floor identity.")
    a = analyze_dxf_structure(dxf_bytes, filename)
    dec = [
        {
            "entity_id": e["entity_id"],
            "review_role": e["suggested_role"],
            "included": e["included"],
            "reviewed": False,
        }
        for e in a["entities"]
    ]
    c = build_dxf_candidate_model(
        a,
        dec,
        metres_per_drawing_unit=scale,
        units_confirmed=True,
        layer_dimensions_confirmed=True,
        project_fields=project_fields or {},
    )
    c["floor_identity"] = floor_identity
    c["floor_identity_label_ar"] = {
        "ground": "الدور الأرضي",
        "typical": "الدور المتكرر",
        "basement": "البدروم",
        "roof": "السطح",
    }[floor_identity]
    c["source_preview_png"] = render_dxf_preview_png(dxf_bytes, filename)
    c["layer_contract"]["standard_confirmed_by_user"] = True
    c["plan_warnings"] = []
    if not (a.get("architectural_intake") or {}).get("plan_title_candidates"):
        c["plan_warnings"].append("عنوان الدور على Layer TEXT يحتاج تأكيدًا.")
    if c["geometry_to_layer_size_check"].get("mismatches"):
        c["plan_warnings"].append("مقاسات بعض الأعمدة لا تطابق الأبعاد المرسومة.")
    c["status"] = "FLOOR_PLAN_DRAFT_LAYER_MAPPED_NEEDS_GEOMETRY_REVIEW"
    return c


def validate_building_stack_config(
    config, *, has_ground_plan, has_typical_plan, has_basement_plan, has_roof_plan
):
    errors = []
    warnings = []
    # Explicit checks (not `assert`): asserts are stripped under `python -O`.
    try:
        n = int(config.get("above_ground_story_count", 0))
    except (TypeError, ValueError):
        n = 0
    if not 1 <= n <= 100:
        n = 0
        errors.append("عدد الأدوار يجب أن يكون 1 إلى 100 ويشمل الأرضي.")
    if not has_ground_plan:
        errors.append("مسقط الدور الأرضي مطلوب.")
    try:
        gh = float(config["ground_story_height_m"])
    except (KeyError, TypeError, ValueError):
        gh = float("nan")
    if not (math.isfinite(gh) and gh > 0):
        gh = 0
        errors.append("ارتفاع الدور الأرضي مطلوب.")
    mode = config.get("upper_story_height_mode", "uniform")
    upper = []
    if n > 1 and not has_typical_plan and config.get("typical_plan_mode") != "same_as_ground":
        errors.append("ارفع المتكرر أو أكد استخدام الأرضي مرجعًا مؤقتًا.")
    if n > 1:
        try:
            if mode == "individual":
                upper = list(map(float, config.get("upper_story_heights_m", [])))
                if len(upper) != n - 1 or any(not math.isfinite(v) or v <= 0 for v in upper):
                    raise ValueError
            else:
                upper = [float(config.get("typical_story_height_m"))] * (n - 1)
            if any(v <= 0 or not math.isfinite(v) for v in upper):
                raise ValueError
        except Exception:
            errors.append(f"أدخل {n-1} ارتفاعات صحيحة للأدوار العليا.")
            upper = []
    try:
        street = float(config.get("street_datum_elevation_m", 0))
        off = float(config["ground_finished_floor_offset_from_street_m"])
    except (KeyError, TypeError, ValueError):
        street = off = float("nan")
    if not math.isfinite(street + off):
        street = off = 0
        errors.append("منسوب الشارع وفرق تشطيب الأرضي مطلوبان.")
    basement = bool(config.get("basement_enabled", False))
    try:
        bc = int(config.get("basement_count", 1)) if basement else 0
    except (TypeError, ValueError):
        bc = 0
        errors.append("عدد البدرومات غير صالح.")
    if basement and not 1 <= bc <= 10:
        bc = 0
        errors.append("عدد البدرومات يجب أن يكون من 1 إلى 10.")
    try:
        bh = float(config.get("basement_story_height_m", 3.2))
    except (TypeError, ValueError):
        bh = float("nan")
    if basement and not (math.isfinite(bh) and bh > 0):
        errors.append("ارتفاع البدروم غير صالح.")
    if not math.isfinite(bh) or bh <= 0:
        bh = 3.2
    if (
        basement
        and not has_basement_plan
        and config.get("basement_plan_mode") != "ground_footprint_proxy"
    ):
        errors.append("ارفع مسقط البدروم أو أكد المرجع المؤقت.")
    elif basement and not has_basement_plan:
        warnings.append("بصمة الأرضي مرجع مؤقت للبدروم؛ حوائط السند والتربة والمياه غير ممثلة.")
    if not has_roof_plan and config.get("roof_plan_mode") != "typical_proxy":
        errors.append("ارفع مسقط السطح أو أكد المرجع المؤقت.")
    elif not has_roof_plan:
        warnings.append("المتكرر مرجع مؤقت للسطح؛ راجع الخزانات والغرف والفتحات.")
    if config.get("soil_report_status") != "available":
        warnings.append("تقرير التربة غير مؤكد؛ لا يمكن اختيار أساس نهائي.")
    if not config.get("wind_basis") or not config.get("seismic_basis"):
        warnings.append("أساس الرياح والزلازل غير مكتمل.")
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "normalized": {
            "above_ground_story_count": n,
            "ground_story_height_m": gh,
            "upper_story_heights_m": upper,
            "story_heights_from_ground_to_roof_m": [gh] + upper,
            "basement_enabled": basement,
            "basement_count": bc,
            "basement_story_heights_m": [bh] * bc,
            "street_datum_elevation_m": street,
            "ground_finished_floor_offset_from_street_m": off,
            "ground_finished_floor_elevation_m": street + off,
        },
    }


def _box(c):
    return (c.get("geometry_m") or {}).get("bbox") or {}


def _points(c):
    return (c.get("geometry_m") or {}).get("points") or []


def _center(c):
    b = _box(c)
    return ((b["min_x"] + b["max_x"]) / 2, (b["min_y"] + b["max_y"]) / 2) if b else None


def _offset(g, p):
    def bounds(plan, roles=None):
        b = [
            _box(c)
            for c in plan.get("components", [])
            if _box(c) and (roles is None or c.get("role") in roles)
        ]
        return (
            (
                min(x["min_x"] for x in b),
                min(x["min_y"] for x in b),
                max(x["max_x"] for x in b),
                max(x["max_y"] for x in b),
            )
            if b
            else None
        )

    # Align on the column footprint when both plans have columns: a stair core, annotation or
    # one extra wall must not shift the whole floor away from the columns below it.
    a, b = bounds(g, {"column"}), bounds(p, {"column"})
    basis_columns = bool(a and b)
    if not basis_columns:
        a, b = bounds(g), bounds(p)
    if not a or not b:
        return 0.0, 0.0, ["تعذر مطابقة أصول المساقط."]
    dx, dy = a[0] - b[0], a[1] - b[1]
    w = []
    if not basis_columns:
        w.append("المحاذاة تمت على كل العناصر لعدم وجود أعمدة في أحد المسقطين.")
    if abs((a[2] - a[0]) - (b[2] - b[0])) > 0.15 or abs((a[3] - a[1]) - (b[3] - b[1])) > 0.15:
        w.append("امتداد المسقط مختلف؛ لم يتم تحجيم الرسم.")
    if abs(dx) + abs(dy) > 0.002:
        w.append(f"تمت ترجمة المسقط فقط dx={dx:.3f}m, dy={dy:.3f}m.")
    return dx, dy, w


def _max_column_matching(adjacency, n_right):
    """Maximum bipartite matching (Kuhn). adjacency[i] = candidate right indices, nearest first.

    Returns {left_index: right_index}. Deterministic for a given input order.
    """
    import sys

    owner = [-1] * n_right
    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old_limit, 4 * len(adjacency) + 200))

    def try_left(i, seen):
        for j in adjacency[i]:
            if j in seen:
                continue
            seen.add(j)
            if owner[j] == -1 or try_left(owner[j], seen):
                owner[j] = i
                return True
        return False

    try:
        for i in range(len(adjacency)):
            try_left(i, set())
    finally:
        sys.setrecursionlimit(old_limit)
    return {owner[j]: j for j in range(n_right) if owner[j] != -1}


def build_multistorey_building_candidate(
    config,
    *,
    ground_plan,
    typical_plan=None,
    basement_plan=None,
    roof_plan=None,
    column_alignment_tolerance_m=0.15,
):
    qa = validate_building_stack_config(
        config,
        has_ground_plan=bool(ground_plan),
        has_typical_plan=bool(typical_plan),
        has_basement_plan=bool(basement_plan),
        has_roof_plan=bool(roof_plan),
    )
    if qa["errors"]:
        raise ValueError("تعذر إنشاء المسودة: " + "؛ ".join(qa["errors"]))
    n = qa["normalized"]["above_ground_story_count"]
    basez = qa["normalized"]["ground_finished_floor_elevation_m"]
    typ = typical_plan or ground_plan
    bas = basement_plan or ground_plan
    roof = roof_plan or typ
    warn = list(qa["warnings"])
    offsets = {}
    for key, pl in [("ground", ground_plan), ("typical", typ), ("basement", bas), ("roof", roof)]:
        dx, dy, w = _offset(ground_plan, pl)
        offsets[key] = (dx, dy)
        warn += [key + ": " + x for x in w]
    if typical_plan is None and n > 1:
        warn.append("تم استخدام الأرضي كمرجع مؤقت للأدوار المتكررة.")
    if roof_plan is None:
        warn.append("المتكرر مرجع مؤقت للسطح.")
    if basement_plan is None and qa["normalized"]["basement_enabled"]:
        warn.append("البدروم يستخدم بصمة الأرضي فقط؛ السند والتربة والمياه غير ممثلة.")
    floor_defs = []
    if qa["normalized"]["basement_enabled"]:
        z = basez
        for i, h in enumerate(qa["normalized"]["basement_story_heights_m"], 1):
            z -= h
            floor_defs.append(
                (
                    f"B{i}",
                    f"البدروم {i}",
                    "basement",
                    z,
                    bas,
                    offsets["basement"],
                    basement_plan is None,
                )
            )
    floor_defs.append(
        ("GF", "الدور الأرضي", "ground", basez, ground_plan, offsets["ground"], False)
    )
    z = basez
    for i, h in enumerate(qa["normalized"]["upper_story_heights_m"], 1):
        z += h
        floor_defs.append(
            (
                f"F{i}",
                f"الدور المتكرر {i}",
                "typical",
                z,
                typ,
                offsets["typical"],
                typical_plan is None,
            )
        )
    rh = (
        qa["normalized"]["upper_story_heights_m"][-1]
        if qa["normalized"]["upper_story_heights_m"]
        else qa["normalized"]["ground_story_height_m"]
    )
    roofz = z + rh
    floor_defs.append(
        ("RF", "منسوب السطح", "roof", roofz, roof, offsets["roof"], roof_plan is None)
    )
    floor_defs.sort(key=lambda x: x[3])
    instances = []
    segments = []
    checks = []
    previous = None
    for floor, label, kind, elev, pl, (dx, dy), proxy in floor_defs:
        comps = []
        for c in pl.get("components", []):
            role = c.get("role")
            if role not in {"column", "beam", "wall", "slab_outline", "opening", "grid_axis"}:
                continue
            pts = _points(c)
            p3 = [[float(p[0]) + dx, float(p[1]) + dy, float(elev)] for p in pts]
            cen = _center(c)
            comps.append(
                {
                    "component_3d_id": f"{floor}:{c.get('candidate_id')}",
                    "source_component_id": c.get("candidate_id"),
                    "source_entity_id": c.get("source_entity_id"),
                    "floor_id": floor,
                    "role": role,
                    "source_layer": c.get("source_layer"),
                    "points_3d_m": p3,
                    "center_3d_m": [cen[0] + dx, cen[1] + dy, elev] if cen else None,
                    "geometry_m": {
                        "points": [[p[0] + dx, p[1] + dy] for p in pts],
                        "bbox": (
                            {k: (v + dx if k.endswith("x") else v + dy) for k, v in _box(c).items()}
                            if _box(c)
                            else None
                        ),
                        "closed": bool((c.get("geometry_m") or {}).get("closed", False)),
                    },
                    "section_cm_as_drawn": c.get("declared_dimensions_cm")
                    or c.get("section_cm_as_drawn"),
                    "proxy_geometry": proxy,
                    "design_status": "NOT_DESIGNED",
                    "review_status": "REQUIRES_ENGINEER_REVIEW",
                }
            )
        curr = {
            "floor_id": floor,
            "label_ar": label,
            "kind": kind,
            "elevation_m": elev,
            "source_filename": (pl.get("source_dxf") or {}).get("filename"),
            "plan_template": kind,
            "proxy_plan": proxy,
            "origin_translation_m": {"dx": dx, "dy": dy},
            "components": comps,
            "component_counts": dict(Counter(x["role"] for x in comps)),
            "review_status": "DRAFT_REQUIRES_ENGINEER_REVIEW",
        }
        instances.append(curr)
        if previous:
            lows = [
                c for c in previous["components"] if c["role"] == "column" and c.get("center_3d_m")
            ]
            highs = [c for c in comps if c["role"] == "column" and c.get("center_3d_m")]
            used = set()
            matches = []
            # One-to-one assignment that maximises the number of matched columns inside the
            # tolerance (augmenting paths), preferring the nearest partner first. Per-column
            # greedy choices leave columns unmatched when two lower columns compete for the
            # same upper one even though a full matching exists.
            adjacency = []
            for lo in lows:
                near = sorted(
                    (
                        math.hypot(
                            lo["center_3d_m"][0] - hi["center_3d_m"][0],
                            lo["center_3d_m"][1] - hi["center_3d_m"][1],
                        ),
                        hi_i,
                    )
                    for hi_i, hi in enumerate(highs)
                )
                adjacency.append([hi_i for d, hi_i in near if d <= column_alignment_tolerance_m])
            assigned = _max_column_matching(adjacency, len(highs))
            for li in sorted(assigned):
                lo, hi = lows[li], highs[assigned[li]]
                used.add(hi["component_3d_id"])
                matches.append((lo, hi))
                segments.append(
                    {
                        "segment_id": f"COLSEG-{len(segments)+1:04d}",
                        "lower_floor_id": previous["floor_id"],
                        "upper_floor_id": floor,
                        "lower_component_id": lo["component_3d_id"],
                        "upper_component_id": hi["component_3d_id"],
                        "mark": f"V-C{len(segments)+1:03d}",
                        "start_xyz_m": lo["center_3d_m"],
                        "end_xyz_m": hi["center_3d_m"],
                        "height_m": elev - previous["elevation_m"],
                        "lower_section_cm": lo.get("section_cm_as_drawn"),
                        "upper_section_cm": hi.get("section_cm_as_drawn"),
                        "section_consistency": (
                            "MATCH"
                            if lo.get("section_cm_as_drawn") == hi.get("section_cm_as_drawn")
                            else "SECTION_CHANGES_REQUIRES_DESIGN_REVIEW"
                        ),
                        "analysis_status": "GEOMETRIC_ONLY_NOT_DESIGNED",
                    }
                )
            checks.append(
                {
                    "lower_floor_id": previous["floor_id"],
                    "upper_floor_id": floor,
                    "lower_column_count": len(lows),
                    "upper_column_count": len(highs),
                    "matched_column_count": len(matches),
                    "lower_unmatched_column_ids": [
                        x["component_3d_id"] for x in lows if not any(x is m[0] for m in matches)
                    ],
                    "upper_unmatched_column_ids": [
                        x["component_3d_id"] for x in highs if x["component_3d_id"] not in used
                    ],
                    "tolerance_m": column_alignment_tolerance_m,
                    "status": (
                        "ALL_COLUMN_CENTRES_MATCH_WITHIN_TOLERANCE"
                        if len(matches) == len(lows) == len(highs)
                        else "MATCHED_WITH_UNMATCHED_REVIEW"
                    ),
                }
            )
        previous = curr
    critical = [
        "تأكيد وظيفة كل حائط واتصالات الكمرات والأعمدة.",
        "نوع البلاطات وسمكها والفتحات والأحمال.",
        "خواص المواد وحالات الأحمال والكود المعتمد.",
        "تحليل الرياح والزلازل والاستقرار والـ diaphragms.",
        "تقرير تربة ومياه جوفية وهبوط وطفو وتأسيس.",
        "تصميم المقاومة والخدمة والتسليح غير منفذ.",
    ]
    if qa["normalized"]["basement_enabled"]:
        critical.append("مسقط بدروم وحوائط سند وضغط تربة ومياه ومنسوب الحفر.")
    if typical_plan is None and n > 1:
        critical.append("مسقط متكرر مستقل غير متوفر؛ الأرضي مرجع مؤقت.")
    if roof_plan is None:
        critical.append("مسقط السطح المستقل غير متوفر.")
    return {
        "schema_version": "structural_building_stack_candidate/0.18.0",
        "status": "MULTISTOREY_3D_CANDIDATE_NEEDS_ENGINEER_REVIEW_NOT_FOR_CONSTRUCTION",
        "project": {
            k: config.get(k)
            for k in (
                "project_name",
                "location",
                "building_use",
                "code_reference",
                "concrete_strength_mpa",
                "steel_yield_strength_mpa",
            )
        },
        "building_configuration": qa["normalized"],
        "plan_instances": instances,
        "levels": [{k: v for k, v in x.items() if k != "components"} for x in instances],
        "column_segments": segments,
        "vertical_continuity_checks": checks,
        "foundation_assessment": {
            "user_candidate_system": config.get("foundation_system_candidate", "not_selected"),
            "selected_final_foundation": None,
            "status": "GEOTECHNICAL_AND_STRUCTURAL_DESIGN_REQUIRED_NOT_SELECTED",
            "notes": ["وجود البدروم لا يحدد اللبشة تلقائيًا؛ وعدم وجوده لا يحدد القواعد المنفصلة."],
        },
        "counts": {
            "above_ground_occupied_floor_plans": n,
            "repeated_typical_plan_instances": n - 1,
            "basement_levels": qa["normalized"]["basement_count"],
            "plan_levels_including_basement_and_roof": len(instances),
            "column_segments": len(segments),
            "component_totals_by_role": dict(
                Counter(c["role"] for l in instances for c in l["components"])
            ),
        },
        "vertical_3d_extents": {
            "lowest_plan_level_m": min(x["elevation_m"] for x in instances),
            "roof_level_m": roofz,
            "total_height_above_street_to_roof_m": roofz
            - qa["normalized"]["street_datum_elevation_m"],
        },
        "critical_missing_inputs": critical,
        "warnings": list(dict.fromkeys(warn)),
        "review_gate": {
            "human_review_required": True,
            "analysis_ready": False,
            "analysis_blockers": [
                "هذه مسودة هندسية فقط وليست نموذج عناصر محددة/FE؛ لا توجد قيود وصلابة وديافرام أو أحمال."
            ],
        },
    }


def render_building_stack_preview_png(model, *, width=1200, height=900):
    lev = model.get("plan_instances", [])
    pts = [p for l in lev for c in l["components"] for p in c.get("points_3d_m", [])]
    if not pts:
        raise ValueError("No 3D candidate geometry.")

    def raw(p):
        return p[0] - p[1], 0.5 * (p[0] + p[1]) - 0.8 * p[2]

    rp = [raw(p) for p in pts]
    mnx, mxx = min(x[0] for x in rp), max(x[0] for x in rp)
    mny, mxy = min(x[1] for x in rp), max(x[1] for x in rp)
    s = min((width - 100) / max(mxx - mnx, 0.1), (height - 130) / max(mxy - mny, 0.1))

    def px(p):
        x, y = raw(p)
        return int(50 + (x - mnx) * s), int(50 + (mxy - y) * s)

    im = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(im)
    f = ImageFont.load_default()
    d.rectangle((10, 10, width - 10, height - 10), outline="#cbd5de")
    d.text((25, 20), "STRUCTURAL STUDIO / 3D CANDIDATE / REVIEW ONLY", fill="#20384c", font=f)
    colors = {
        "column": "#d38b27",
        "beam": "#2475a7",
        "wall": "#76628e",
        "slab_outline": "#16826b",
        "opening": "#b55bad",
        "grid_axis": "#9aa6b2",
    }
    for l in lev:
        for c in l["components"]:
            pp = c.get("points_3d_m", [])
            if len(pp) > 1:
                try:
                    d.line([px(p) for p in pp], fill=colors.get(c["role"], "#333"), width=2)
                except Exception:
                    pass
            if c.get("center_3d_m"):
                x, y = px(c["center_3d_m"])
                d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=colors["column"])
    for seg in model.get("column_segments", []):
        if seg.get("start_xyz_m") and seg.get("end_xyz_m"):
            d.line((px(seg["start_xyz_m"]), px(seg["end_xyz_m"])), fill="#d38b27", width=3)
    for i, l in enumerate(lev):
        d.text(
            (25, 45 + i * 16), f"{l['floor_id']} Z={l['elevation_m']:.2f}m", fill="#20384c", font=f
        )
    d.text(
        (25, height - 25),
        "SCHEMATIC ONLY - NOT A FINITE ELEMENT MODEL - NOT FOR CONSTRUCTION",
        fill="#a12828",
        font=f,
    )
    o = BytesIO()
    im.save(o, format="PNG")
    return o.getvalue()


def create_building_stack_review_package(model, preview_png, source_files=None):
    files = {
        "building_stack_candidate.json": json.dumps(
            model, ensure_ascii=False, indent=2, default=str
        ).encode(),
        "building_stack_preview.png": preview_png,
    }
    out = StringIO(newline="")
    fields = ["floor_id", "label_ar", "kind", "elevation_m", "source_filename", "proxy_plan"]
    w = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for l in model.get("plan_instances", []):
        w.writerow(l)
    files["building_stack_levels.csv"] = out.getvalue().encode("utf-8-sig")
    for n, b in (source_files or {}).items():
        if str(n).lower().endswith(".dxf"):
            files["source_plans/" + str(n).split("/")[-1]] = b
    files["manifest_sha256.json"] = json.dumps(
        {n: hashlib.sha256(b).hexdigest() for n, b in sorted(files.items())}, indent=2
    ).encode()
    z = BytesIO()
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
        for n, b in files.items():
            f.writestr(n, b)
    with zipfile.ZipFile(BytesIO(z.getvalue())) as f:
        if f.testzip():
            raise RuntimeError("Invalid candidate ZIP.")
    return z.getvalue()
