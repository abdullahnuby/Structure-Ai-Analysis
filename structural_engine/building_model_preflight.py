"""Review-first connectivity QA for a multi-storey architectural building candidate.

This module audits geometry and candidate member connectivity only. It does not turn
architectural entities into a solver-ready finite-element model and never marks a
building analysis-ready. Walls are not assumed to be structural shear walls, slabs
are not assumed to be rigid diaphragms, and foundations/restraints are never guessed.
"""

from __future__ import annotations

from collections import Counter
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
import csv
import hashlib
import json
import math
import zipfile

import ezdxf
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

RELEASE_STATUS = "GEOMETRIC_CONNECTIVITY_PRECHECK_ONLY_NOT_FOR_CONSTRUCTION"


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _bbox_xy(comp: dict[str, Any]) -> dict[str, float] | None:
    pts = comp.get("points_3d_m") or []
    if pts:
        try:
            xs = [float(p[0]) for p in pts]
            ys = [float(p[1]) for p in pts]
            if all(math.isfinite(v) for v in xs + ys):
                return {"min_x": min(xs), "max_x": max(xs), "min_y": min(ys), "max_y": max(ys)}
        except (TypeError, ValueError, IndexError):
            pass
    geom = comp.get("geometry_m") or {}
    bbox = geom.get("bbox") or {}
    try:
        vals = {k: float(bbox[k]) for k in ("min_x", "max_x", "min_y", "max_y")}
        return vals if all(math.isfinite(v) for v in vals.values()) else None
    except (TypeError, ValueError, KeyError):
        return None


def _points_xy(comp: dict[str, Any]) -> list[list[float]]:
    pts = comp.get("points_3d_m")
    if isinstance(pts, list) and pts:
        try:
            return [[float(p[0]), float(p[1])] for p in pts]
        except (TypeError, ValueError, IndexError):
            return []
    pts = (comp.get("geometry_m") or {}).get("points") or []
    try:
        return [[float(p[0]), float(p[1])] for p in pts]
    except (TypeError, ValueError, IndexError):
        return []


def _center_xy(comp: dict[str, Any]) -> tuple[float, float] | None:
    center = comp.get("center_3d_m")
    if isinstance(center, list) and len(center) >= 2 and _finite(center[0]) and _finite(center[1]):
        return float(center[0]), float(center[1])
    box = _bbox_xy(comp)
    if box:
        return (box["min_x"] + box["max_x"]) / 2, (box["min_y"] + box["max_y"]) / 2
    return None


def _point_rect_gap(x: float, y: float, box: dict[str, float]) -> float:
    dx = max(box["min_x"] - x, 0.0, x - box["max_x"])
    dy = max(box["min_y"] - y, 0.0, y - box["max_y"])
    return math.hypot(dx, dy)


def _point_segment_distance(
    px: float, py: float, a: list[float], b: list[float]
) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = dx * dx + dy * dy
    if den <= 1e-18:
        return math.hypot(px - a[0], py - a[1]), 0.0
    t = ((px - a[0]) * dx + (py - a[1]) * dy) / den
    tc = max(0.0, min(1.0, t))
    qx, qy = a[0] + tc * dx, a[1] + tc * dy
    return math.hypot(px - qx, py - qy), t


def _closed_polygon(points: list[list[float]]) -> bool:
    return (
        len(points) >= 4
        and math.hypot(points[0][0] - points[-1][0], points[0][1] - points[-1][1]) <= 1e-6
    )


def _point_in_polygon(point: tuple[float, float], poly: list[list[float]]) -> bool:
    if len(poly) >= 2 and math.hypot(poly[0][0] - poly[-1][0], poly[0][1] - poly[-1][1]) <= 1e-6:
        poly = poly[:-1]
    x, y = point
    inside = False
    if len(poly) < 3:
        return False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-30) + xi):
            inside = not inside
        j = i
    return inside


def _make_issue(
    code: str, severity: str, floor_id: str | None, component_id: str | None, message: str
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "floor_id": floor_id,
        "component_id": component_id,
        "message_ar": message,
    }


def audit_building_candidate_connectivity(
    building_model: dict[str, Any],
    *,
    geometric_gap_tolerance_m: float = 0.05,
    centerline_tolerance_m: float = 0.03,
    section_dimension_tolerance_m: float = 0.03,
) -> dict[str, Any]:
    """Audit a stacked candidate's geometry/topology; do not generate a solver model.

    Beam endpoints must be two-point plan centre-lines to be evaluated. Contact with a
    column footprint is distinguished from centreline alignment so the user sees when
    rigid offsets/eccentricities would need explicit modelling.
    """
    for name, value in (
        ("geometric_gap_tolerance_m", geometric_gap_tolerance_m),
        ("centerline_tolerance_m", centerline_tolerance_m),
        ("section_dimension_tolerance_m", section_dimension_tolerance_m),
    ):
        if not _finite(value) or float(value) <= 0 or float(value) > 1:
            raise ValueError(f"{name} must be finite and in (0, 1] m.")
    levels = building_model.get("plan_instances") if isinstance(building_model, dict) else None
    if not isinstance(levels, list) or not levels:
        raise ValueError("The building candidate must contain non-empty plan_instances.")

    issues: list[dict[str, Any]] = []
    node_candidates: list[dict[str, Any]] = []
    beam_end_records: list[dict[str, Any]] = []
    beam_records: list[dict[str, Any]] = []
    section_records: list[dict[str, Any]] = []
    slab_records: list[dict[str, Any]] = []
    role_counts: Counter[str] = Counter()
    supports_by_floor: dict[str, list[dict[str, Any]]] = {}
    beam_segments_by_floor: dict[str, list[dict[str, Any]]] = {}

    ordered_levels = sorted(levels, key=lambda item: float(item.get("elevation_m", 0.0)))
    for level in ordered_levels:
        floor_id = str(level.get("floor_id", "?"))
        comps = level.get("components", [])
        if not isinstance(comps, list):
            issues.append(
                _make_issue(
                    "INVALID_LEVEL_COMPONENTS",
                    "BLOCKER",
                    floor_id,
                    None,
                    "قائمة مكونات الدور غير صالحة.",
                )
            )
            continue
        columns: list[dict[str, Any]] = []
        beams: list[dict[str, Any]] = []
        walls: list[dict[str, Any]] = []
        slab_polys: list[tuple[dict[str, Any], list[list[float]]]] = []
        openings: list[dict[str, Any]] = []
        for comp in comps:
            role = str(comp.get("role", "unknown"))
            role_counts[role] += 1
            cid = str(comp.get("component_3d_id", comp.get("source_component_id", "?")))
            if comp.get("proxy_geometry") or level.get("proxy_plan"):
                # one blocker per level, not one per entity; level warning is emitted below.
                pass
            if role == "column":
                box, center = _bbox_xy(comp), _center_xy(comp)
                if (
                    box is None
                    or center is None
                    or (box["max_x"] - box["min_x"] <= 1e-6)
                    or (box["max_y"] - box["min_y"] <= 1e-6)
                ):
                    issues.append(
                        _make_issue(
                            "COLUMN_GEOMETRY_NOT_RECTANGULAR_OR_MISSING",
                            "BLOCKER",
                            floor_id,
                            cid,
                            "هندسة العمود لا تعطي بصمة مستطيلة/مركزًا واضحًا؛ يلزم إصلاح الرسم أو مراجعة يدوية.",
                        )
                    )
                    continue
                columns.append({"component": comp, "box": box, "center": center, "id": cid})
                node_candidates.append(
                    {
                        "node_candidate_id": f"N-{floor_id}-{cid}",
                        "floor_id": floor_id,
                        "x_m": center[0],
                        "y_m": center[1],
                        "z_m": float(level.get("elevation_m", 0.0)),
                        "source_component_id": cid,
                        "node_type": "COLUMN_CENTRE_CANDIDATE",
                        "restraints_assigned": False,
                        "analysis_ready": False,
                    }
                )
                dims = comp.get("section_cm_as_drawn") or {}
                try:
                    declared = sorted([float(dims["width"]) / 100.0, float(dims["depth"]) / 100.0])
                    drawn = sorted([box["max_x"] - box["min_x"], box["max_y"] - box["min_y"]])
                    deltas = [abs(declared[i] - drawn[i]) for i in (0, 1)]
                    ok = max(deltas) <= section_dimension_tolerance_m
                    status = "GEOMETRY_MATCHES_LAYER_DIMS" if ok else "DIMENSIONS_MISMATCH_REVIEW"
                    section_records.append(
                        {
                            "floor_id": floor_id,
                            "component_id": cid,
                            "role": role,
                            "declared_dim_a_m": declared[0],
                            "declared_dim_b_m": declared[1],
                            "drawn_dim_a_m": drawn[0],
                            "drawn_dim_b_m": drawn[1],
                            "max_abs_delta_m": max(deltas),
                            "status": status,
                        }
                    )
                    if not ok:
                        issues.append(
                            _make_issue(
                                "COLUMN_SECTION_LAYER_GEOMETRY_MISMATCH",
                                "BLOCKER",
                                floor_id,
                                cid,
                                f"أبعاد بصمة العمود لا تطابق المقاسات المكتوبة في الطبقة ضمن سماحية {section_dimension_tolerance_m:.3f} م.",
                            )
                        )
                except (KeyError, TypeError, ValueError):
                    section_records.append(
                        {
                            "floor_id": floor_id,
                            "component_id": cid,
                            "role": role,
                            "status": "SECTION_DIMS_MISSING_OR_INVALID",
                        }
                    )
                    issues.append(
                        _make_issue(
                            "COLUMN_SECTION_DIMS_MISSING",
                            "BLOCKER",
                            floor_id,
                            cid,
                            "مقاس العمود غير قابل للقراءة؛ يلزم تصحيح اسم الطبقة مثل column 60x30.",
                        )
                    )
            elif role == "beam":
                pts = _points_xy(comp)
                z_vals = [
                    float(p[2])
                    for p in comp.get("points_3d_m", [])
                    if isinstance(p, list) and len(p) > 2 and _finite(p[2])
                ]
                if len(pts) != 2 or (len(z_vals) == 2 and abs(z_vals[0] - z_vals[1]) > 1e-6):
                    issues.append(
                        _make_issue(
                            "BEAM_NOT_SIMPLE_HORIZONTAL_CENTRELINE",
                            "BLOCKER",
                            floor_id,
                            cid,
                            "الكمرة ليست خط محور أفقيًا بنقطتي نهاية واضحتين؛ يلزم تعديلها إلى centreline أو تصنيفها يدويًا.",
                        )
                    )
                    continue
                if math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]) <= 1e-6:
                    issues.append(
                        _make_issue(
                            "ZERO_LENGTH_BEAM_CANDIDATE",
                            "BLOCKER",
                            floor_id,
                            cid,
                            "طول الكمرة المرشحة يساوي صفرًا.",
                        )
                    )
                    continue
                dims = comp.get("section_cm_as_drawn") or {}
                try:
                    width_m, depth_m = float(dims["width"]) / 100.0, float(dims["depth"]) / 100.0
                    if width_m <= 0 or depth_m <= 0:
                        raise ValueError
                    section_status = "SECTION_DIMS_PARSED_NEED_CONFIRMED"
                except (KeyError, TypeError, ValueError):
                    width_m = depth_m = None
                    section_status = "SECTION_DIMS_MISSING_OR_INVALID"
                    issues.append(
                        _make_issue(
                            "BEAM_SECTION_DIMS_MISSING",
                            "BLOCKER",
                            floor_id,
                            cid,
                            "مقاس الكمرة غير قابل للقراءة من الطبقة.",
                        )
                    )
                beam = {
                    "component": comp,
                    "id": cid,
                    "points": pts,
                    "width_m": width_m,
                    "depth_m": depth_m,
                }
                beams.append(beam)
                beam_records.append(
                    {
                        "floor_id": floor_id,
                        "component_id": cid,
                        "source_layer": comp.get("source_layer"),
                        "length_m": math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]),
                        "width_m": width_m,
                        "depth_m": depth_m,
                        "section_status": section_status,
                        "geometry_status": "TWO_POINT_PLAN_CENTRELINE",
                    }
                )
            elif role == "wall":
                walls.append({"component": comp, "id": cid})
            elif role == "slab_outline":
                pts = _points_xy(comp)
                is_closed = bool(comp.get("geometry_closed")) or _closed_polygon(pts)
                poly_record = {"component": comp, "id": cid, "points": pts, "closed": is_closed}
                if is_closed:
                    slab_polys.append((comp, pts))
                slab_records.append(
                    {
                        "floor_id": floor_id,
                        "component_id": cid,
                        "role": role,
                        "vertex_count": len(pts),
                        "closed_polygon": is_closed,
                        "status": (
                            "CLOSED_POLYGON_CANDIDATE"
                            if is_closed
                            else "BOUNDARY_NOT_CLOSED_REVIEW"
                        ),
                    }
                )
                if not is_closed:
                    issues.append(
                        _make_issue(
                            "SLAB_BOUNDARY_NOT_CLOSED",
                            "BLOCKER",
                            floor_id,
                            cid,
                            "حد البلاطة غير مغلق؛ لا يمكن اعتماد المساحة أو موقع الفتحات منه.",
                        )
                    )
            elif role == "opening":
                openings.append(comp)
        supports_by_floor[floor_id] = columns
        beam_segments_by_floor[floor_id] = beams
        if level.get("proxy_plan"):
            issues.append(
                _make_issue(
                    "PROXY_PLAN_USED",
                    "BLOCKER",
                    floor_id,
                    None,
                    f"الدور {floor_id} يعتمد على مسقط proxy؛ لا يُعتبر مطابقًا إنشائيًا قبل مراجعة فتحاته وعناصره.",
                )
            )
        if walls:
            issues.append(
                _make_issue(
                    "WALL_STRUCTURAL_ROLE_UNCONFIRMED",
                    "BLOCKER",
                    floor_id,
                    None,
                    f"يوجد {len(walls)} حائط مرشح في {floor_id}؛ يجب تصنيف كل حائط: قاطع/ملء/حامل/قص/سند قبل التحليل.",
                )
            )
        if not slab_polys:
            issues.append(
                _make_issue(
                    "NO_CLOSED_SLAB_OUTLINE",
                    "BLOCKER",
                    floor_id,
                    None,
                    f"لا يوجد حد بلاطة مغلق واضح في {floor_id}; لا يمكن توزيع أحمال البلاطة أو تعريف ديافرام.",
                )
            )
        for opening in openings:
            op_pts = _points_xy(opening)
            if not op_pts:
                issues.append(
                    _make_issue(
                        "OPENING_GEOMETRY_MISSING",
                        "BLOCKER",
                        floor_id,
                        str(opening.get("component_3d_id", "?")),
                        "هندسة الفتحة غير واضحة.",
                    )
                )
                continue
            # Only centroid-like point check is available; this is a screen, not polygon clipping.
            cx = sum(p[0] for p in op_pts) / len(op_pts)
            cy = sum(p[1] for p in op_pts) / len(op_pts)
            if slab_polys and not any(_point_in_polygon((cx, cy), poly) for _, poly in slab_polys):
                issues.append(
                    _make_issue(
                        "OPENING_OUTSIDE_SLAB_OR_NOT_ENCLOSED",
                        "BLOCKER",
                        floor_id,
                        str(opening.get("component_3d_id", "?")),
                        "مركز الفتحة لا يقع داخل حد بلاطة مغلق؛ راجع طبقة الفتحة وحدود البلاطة.",
                    )
                )

    # Beam-end connectivity: first column footprints/centrelines, then beam-network candidates.
    for level in ordered_levels:
        floor_id = str(level.get("floor_id", "?"))
        cols = supports_by_floor.get(floor_id, [])
        beams = beam_segments_by_floor.get(floor_id, [])
        for beam in beams:
            for end_idx, point in enumerate(beam["points"], start=1):
                # Most precise support first: actual column footprint, not a guessed grid node.
                candidates = []
                for col in cols:
                    gap = _point_rect_gap(point[0], point[1], col["box"])
                    if gap <= float(geometric_gap_tolerance_m):
                        center_gap = math.hypot(
                            point[0] - col["center"][0], point[1] - col["center"][1]
                        )
                        candidates.append((gap, center_gap, col))
                candidates.sort(key=lambda row: (row[0], row[1]))
                if candidates:
                    gap, center_gap, col = candidates[0]
                    if center_gap <= float(centerline_tolerance_m):
                        conn = "COLUMN_CENTRELINE_MATCH"
                        severity = "INFO"
                        message = "نهاية الكمرة متطابقة مع مركز العمود ضمن السماحية الهندسية."
                    else:
                        conn = "COLUMN_FOOTPRINT_CONTACT_OFFSET_REQUIRES_REVIEW"
                        severity = "REVIEW"
                        message = "نهاية الكمرة تلامس بصمة العمود لكن لا تطابق مركزه؛ يلزم تحديد هل نستخدم rigid offset/eccentricity أم تعديل محور الرسم."
                        issues.append(
                            _make_issue(
                                "BEAM_COLUMN_CENTRELINE_OFFSET",
                                "BLOCKER",
                                floor_id,
                                beam["id"],
                                message,
                            )
                        )
                    record = {
                        "floor_id": floor_id,
                        "beam_component_id": beam["id"],
                        "end_index": end_idx,
                        "x_m": point[0],
                        "y_m": point[1],
                        "connection_type": conn,
                        "connected_component_id": col["id"],
                        "distance_to_footprint_m": gap,
                        "distance_to_column_centre_m": center_gap,
                        "status": severity,
                    }
                else:
                    network_candidates = []
                    for other in beams:
                        if other["id"] == beam["id"]:
                            continue
                        dist, t = _point_segment_distance(
                            point[0], point[1], other["points"][0], other["points"][1]
                        )
                        if dist <= float(geometric_gap_tolerance_m) and -1e-6 <= t <= 1 + 1e-6:
                            network_candidates.append((dist, t, other))
                    if network_candidates:
                        dist, t, other = min(network_candidates, key=lambda row: row[0])
                        interior = 0.03 < t < 0.97
                        conn = (
                            "BEAM_INTERIOR_JOINT_REQUIRES_SPLIT"
                            if interior
                            else "BEAM_TO_BEAM_ENDPOINT_CANDIDATE"
                        )
                        status = "REVIEW"
                        issues.append(
                            _make_issue(
                                "BEAM_ENDPOINT_JOINS_BEAM_NETWORK",
                                "BLOCKER" if interior else "REVIEW",
                                floor_id,
                                beam["id"],
                                (
                                    "نهاية الكمرة تلتقي بداخل كمرة أخرى؛ يجب تقسيم العضو عند العقدة والتحقق من الاتصال."
                                    if interior
                                    else "نهاية الكمرة تلتقي بكمرة أخرى؛ يلزم تأكيد اتصال العقدة."
                                ),
                            )
                        )
                        record = {
                            "floor_id": floor_id,
                            "beam_component_id": beam["id"],
                            "end_index": end_idx,
                            "x_m": point[0],
                            "y_m": point[1],
                            "connection_type": conn,
                            "connected_component_id": other["id"],
                            "distance_to_footprint_m": None,
                            "distance_to_column_centre_m": None,
                            "status": status,
                            "distance_to_beam_m": dist,
                        }
                    else:
                        record = {
                            "floor_id": floor_id,
                            "beam_component_id": beam["id"],
                            "end_index": end_idx,
                            "x_m": point[0],
                            "y_m": point[1],
                            "connection_type": "UNSUPPORTED_BEAM_END",
                            "connected_component_id": None,
                            "distance_to_footprint_m": None,
                            "distance_to_column_centre_m": None,
                            "status": "BLOCKER",
                        }
                        issues.append(
                            _make_issue(
                                "UNSUPPORTED_BEAM_END",
                                "BLOCKER",
                                floor_id,
                                beam["id"],
                                f"نهاية الكمرة رقم {end_idx} لا تلتقي بعمود أو شبكة كمرات ضمن {geometric_gap_tolerance_m:.3f} م.",
                            )
                        )
                beam_end_records.append(record)

    # Detect duplicate beam segments within each floor.
    for floor_id, beams in beam_segments_by_floor.items():
        for i, a in enumerate(beams):
            for b in beams[i + 1 :]:
                direct = max(
                    math.dist(a["points"][0], b["points"][0]),
                    math.dist(a["points"][1], b["points"][1]),
                )
                reverse = max(
                    math.dist(a["points"][0], b["points"][1]),
                    math.dist(a["points"][1], b["points"][0]),
                )
                if min(direct, reverse) <= float(centerline_tolerance_m):
                    issues.append(
                        _make_issue(
                            "DUPLICATE_BEAM_CENTRELINES",
                            "BLOCKER",
                            floor_id,
                            a["id"],
                            f"الكمرة المرشحة {a['id']} تتطابق تقريبًا مع {b['id']}؛ احذف التكرار قبل تكوين صلابة النموذج.",
                        )
                    )

    for check in building_model.get("vertical_continuity_checks", []):
        if check.get("status") != "ALL_COLUMN_CENTRES_MATCH_WITHIN_TOLERANCE":
            issues.append(
                _make_issue(
                    "VERTICAL_COLUMN_DISCONTINUITY",
                    "BLOCKER",
                    str(check.get("upper_floor_id")),
                    None,
                    f"عدم تطابق أعمدة بين {check.get('lower_floor_id')} و{check.get('upper_floor_id')}; لا يتم وصلها أو افتراض transfer تلقائيًا.",
                )
            )
    for segment in building_model.get("column_segments", []):
        if segment.get("section_consistency") != "MATCH":
            issues.append(
                _make_issue(
                    "COLUMN_SECTION_CHANGE_REQUIRES_DESIGN",
                    "BLOCKER",
                    str(segment.get("upper_floor_id")),
                    str(segment.get("upper_component_id")),
                    "مقاس العمود يتغير بين مستويين؛ يلزم تدقيق انتقال القطاع وموضعه وتصميم منطقة الانتقال.",
                )
            )

    # Assemble an explicitly non-analysis candidate connectivity graph. A beam endpoint
    # only maps to a candidate column-centre node when the centreline actually matches.
    end_by_key = {
        (r["floor_id"], r["beam_component_id"], r["end_index"]): r for r in beam_end_records
    }
    graph_beams: list[dict[str, Any]] = []
    for beam in beam_records:
        floor_id, comp_id = str(beam["floor_id"]), str(beam["component_id"])
        source = next(
            (b for b in beam_segments_by_floor.get(floor_id, []) if b["id"] == comp_id), None
        )
        if source is None:
            continue
        ends = [end_by_key.get((floor_id, comp_id, idx), {}) for idx in (1, 2)]
        node_ids = []
        for r in ends:
            if r.get("connection_type") == "COLUMN_CENTRELINE_MATCH":
                node_ids.append(f"N-{floor_id}-{r.get('connected_component_id')}")
            else:
                node_ids.append(None)
        graph_beams.append(
            {
                "member_candidate_id": f"MEM-{floor_id}-{comp_id}",
                "member_type": "BEAM_CENTRELINE_CANDIDATE",
                "floor_id": floor_id,
                "source_component_id": comp_id,
                "start_xyz_m": [
                    source["points"][0][0],
                    source["points"][0][1],
                    float(
                        next(x for x in ordered_levels if str(x.get("floor_id")) == floor_id).get(
                            "elevation_m", 0.0
                        )
                    ),
                ],
                "end_xyz_m": [
                    source["points"][1][0],
                    source["points"][1][1],
                    float(
                        next(x for x in ordered_levels if str(x.get("floor_id")) == floor_id).get(
                            "elevation_m", 0.0
                        )
                    ),
                ],
                "i_node_candidate_id": node_ids[0],
                "j_node_candidate_id": node_ids[1],
                "section_width_m": beam.get("width_m"),
                "section_depth_m": beam.get("depth_m"),
                "geometry_connectivity_status": (
                    "COLUMN_NODE_ENDPOINTS_MATCH"
                    if all(node_ids)
                    else "ENDPOINT_CONNECTION_REQUIRES_REVIEW"
                ),
                "solver_ready": False,
            }
        )
    column_graph = []
    node_lookup = {n["node_candidate_id"] for n in node_candidates}
    for seg in building_model.get("column_segments", []):
        lower_id = f"N-{seg.get('lower_floor_id')}-{seg.get('lower_component_id')}"
        upper_id = f"N-{seg.get('upper_floor_id')}-{seg.get('upper_component_id')}"
        column_graph.append(
            {
                "member_candidate_id": seg.get("segment_id"),
                "member_type": "VERTICAL_COLUMN_SEGMENT_CANDIDATE",
                "lower_floor_id": seg.get("lower_floor_id"),
                "upper_floor_id": seg.get("upper_floor_id"),
                "i_node_candidate_id": lower_id if lower_id in node_lookup else None,
                "j_node_candidate_id": upper_id if upper_id in node_lookup else None,
                "start_xyz_m": seg.get("start_xyz_m"),
                "end_xyz_m": seg.get("end_xyz_m"),
                "lower_section_cm": seg.get("lower_section_cm"),
                "upper_section_cm": seg.get("upper_section_cm"),
                "section_consistency": seg.get("section_consistency"),
                "solver_ready": False,
            }
        )
    candidate_graph = {
        "graph_id": "BUILDING_GEOMETRIC_CONNECTIVITY_CANDIDATE_V1",
        "nodes": node_candidates,
        "members": column_graph + graph_beams,
        "graph_status": "GEOMETRIC_CANDIDATE_ONLY_NOT_A_FINITE_ELEMENT_MODEL",
        "nodes_have_restraints": False,
        "member_stiffness_assigned": False,
        "diaphragms_defined": False,
        "loads_assigned": False,
    }

    # Even a geometrically connected frame still lacks these core analysis definitions.
    mandatory_model_gaps = [
        "تحديد صريح للعناصر الإنشائية مقابل المعمارية؛ طبقة wall لا تثبت أنها حائط قص أو حائط حامل.",
        "اختيار محرك العناصر الملائم لكل عنصر: إطار/Plate/Shell/حائط، مع وصلات واتجاهات محاور محلية معتمدة.",
        "تعريف diaphragm لكل دور كصلب/شبه صلب/مرن مع اختبار فرضيته؛ لا يُفترض صلبًا من وجود slab outline.",
        "تعريف درجات الحرية والقيود وقواعد الأساسات/التربة دون تثبيت القواعد تلقائيًا.",
        "خواص المواد والصلابة الفعالة/المتشققة، حالات وتركيبات أحمال موثقة، وأحمال الرياح/الزلازل من أساس رسمي.",
        "تعريف P-Delta والاستقرار والانجراف وعدم الانتظام والتواء المبنى وفق معيار تصميم موثق.",
        "تحقق مستقل من نموذج التحليل على مسائل مرجعية قبل السماح بحكم مقاومة أو خدمة.",
    ]
    blockers = [x for x in issues if x["severity"] == "BLOCKER"]
    reviews = [x for x in issues if x["severity"] == "REVIEW"]
    counts = {
        "levels": len(ordered_levels),
        "components": sum(len(x.get("components", [])) for x in ordered_levels),
        "columns": role_counts.get("column", 0),
        "beams": role_counts.get("beam", 0),
        "walls": role_counts.get("wall", 0),
        "slab_outlines": role_counts.get("slab_outline", 0),
        "openings": role_counts.get("opening", 0),
        "candidate_nodes": len(node_candidates),
        "beam_ends_checked": len(beam_end_records),
        "beam_ends_column_centreline_matched": sum(
            1 for r in beam_end_records if r["connection_type"] == "COLUMN_CENTRELINE_MATCH"
        ),
        "beam_ends_column_footprint_only": sum(
            1
            for r in beam_end_records
            if r["connection_type"] == "COLUMN_FOOTPRINT_CONTACT_OFFSET_REQUIRES_REVIEW"
        ),
        "beam_ends_to_beam_network": sum(
            1
            for r in beam_end_records
            if r["connection_type"]
            in {"BEAM_INTERIOR_JOINT_REQUIRES_SPLIT", "BEAM_TO_BEAM_ENDPOINT_CANDIDATE"}
        ),
        "unsupported_beam_ends": sum(
            1 for r in beam_end_records if r["connection_type"] == "UNSUPPORTED_BEAM_END"
        ),
        "blockers": len(blockers),
        "reviews": len(reviews),
        "informational_issues": sum(1 for x in issues if x["severity"] == "INFO"),
    }
    return {
        "status": RELEASE_STATUS,
        "building_model_id": building_model.get(
            "building_model_id", building_model.get("status", "candidate")
        ),
        "thresholds_m": {
            "geometric_gap_tolerance_m": float(geometric_gap_tolerance_m),
            "centerline_tolerance_m": float(centerline_tolerance_m),
            "section_dimension_tolerance_m": float(section_dimension_tolerance_m),
        },
        "counts": counts,
        "candidate_nodes": node_candidates,
        "candidate_graph": candidate_graph,
        "beam_segments": beam_records,
        "beam_end_connectivity": beam_end_records,
        "section_geometry_checks": section_records,
        "slab_boundary_checks": slab_records,
        "issues": issues,
        "critical_model_gaps": mandatory_model_gaps,
        "analysis_gate": {
            "analysis_ready": False,
            "status": "BLOCKED_NO_APPROVED_ANALYTICAL_MODEL",
            "reason": "التدقيق الحالي هندسي/طوبولوجي فقط ولا يعرّف بعد عناصر FE والصلابة والقيود والديافرام والأحمال.",
        },
        "release": "NOT_FOR_CONSTRUCTION",
    }


def _csv_bytes(rows: list[dict[str, Any]], fallback_fields: list[str]) -> bytes:
    sio = StringIO(newline="")
    fields = list(rows[0].keys()) if rows else fallback_fields
    writer = csv.DictWriter(sio, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return sio.getvalue().encode("utf-8-sig")


def render_connectivity_dxf(building_model: dict[str, Any], result: dict[str, Any]) -> bytes:
    doc = ezdxf.new("R2013")
    msp = doc.modelspace()
    layers = {
        "BEAM_CENTRELINE": 5,
        "COLUMN_FOOTPRINT": 30,
        "COLUMN_NODE_CANDIDATE": 1,
        "CONNECTED_END": 3,
        "REVIEW_END": 2,
        "UNSUPPORTED_END": 1,
        "WALL_ROLE_REVIEW": 6,
        "SLAB_BOUNDARY": 4,
        "LABELS": 7,
    }
    for name, color in layers.items():
        if name not in doc.layers:
            doc.layers.new(name=name, dxfattribs={"color": color})
    records = {
        (r["floor_id"], r["beam_component_id"], r["end_index"]): r
        for r in result["beam_end_connectivity"]
    }
    for level in building_model.get("plan_instances", []):
        floor_id = str(level.get("floor_id", "?"))
        for comp in level.get("components", []):
            role = comp.get("role")
            pts = comp.get("points_3d_m") or []
            if role == "column":
                box = _bbox_xy(comp)
                if box:
                    z = float(level.get("elevation_m", 0.0))
                    corners = [
                        (box["min_x"], box["min_y"], z),
                        (box["max_x"], box["min_y"], z),
                        (box["max_x"], box["max_y"], z),
                        (box["min_x"], box["max_y"], z),
                    ]
                    msp.add_polyline3d(
                        corners, close=True, dxfattribs={"layer": "COLUMN_FOOTPRINT"}
                    )
                center = _center_xy(comp)
                if center:
                    msp.add_circle(
                        (center[0], center[1], float(level.get("elevation_m", 0))),
                        radius=0.05,
                        dxfattribs={"layer": "COLUMN_NODE_CANDIDATE"},
                    )
            elif role == "beam" and len(pts) == 2:
                msp.add_line(tuple(pts[0]), tuple(pts[1]), dxfattribs={"layer": "BEAM_CENTRELINE"})
                for end_idx, p in enumerate(pts, 1):
                    r = records.get((floor_id, str(comp.get("component_3d_id", "?")), end_idx), {})
                    layer = (
                        "CONNECTED_END"
                        if r.get("connection_type") == "COLUMN_CENTRELINE_MATCH"
                        else (
                            "UNSUPPORTED_END"
                            if r.get("connection_type") == "UNSUPPORTED_BEAM_END"
                            else "REVIEW_END"
                        )
                    )
                    msp.add_circle(tuple(p), radius=0.07, dxfattribs={"layer": layer})
            elif role == "slab_outline" and len(pts) >= 3:
                msp.add_polyline3d(
                    [tuple(p) for p in pts], close=True, dxfattribs={"layer": "SLAB_BOUNDARY"}
                )
            elif role == "wall" and len(pts) >= 2:
                msp.add_polyline3d(
                    [tuple(p) for p in pts], close=False, dxfattribs={"layer": "WALL_ROLE_REVIEW"}
                )
        z = float(level.get("elevation_m", 0.0))
        ext_points = [p for c in level.get("components", []) for p in (c.get("points_3d_m") or [])]
        if ext_points:
            minx, miny = min(float(p[0]) for p in ext_points), min(float(p[1]) for p in ext_points)
            msp.add_text(
                f"{floor_id} | Z={z:.3f} m",
                dxfattribs={"layer": "LABELS", "height": 0.25, "insert": (minx, miny - 0.5, z)},
            )
    doc.header["$INSUNITS"] = 6
    out = StringIO()
    doc.write(out)
    return out.getvalue().encode("utf-8")


def render_connectivity_report_pdf(result: dict[str, Any], path: str | Path) -> None:
    doc = SimpleDocTemplate(
        str(path),
        pagesize=landscape(A3),
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=8 * mm,
        bottomMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ConnTitle",
            parent=styles["Title"],
            fontSize=17,
            leading=20,
            textColor=colors.HexColor("#17324D"),
        )
    )
    styles.add(ParagraphStyle(name="ConnBody", parent=styles["BodyText"], fontSize=8, leading=10))
    c = result["counts"]
    story = [
        Paragraph("STRUCTURAL STUDIO — BUILDING CONNECTIVITY PRECHECK", styles["ConnTitle"]),
        Spacer(1, 3 * mm),
        Paragraph(
            f"Status: {result['status']} | Release: NOT FOR CONSTRUCTION | Analysis ready: {result['analysis_gate']['analysis_ready']}",
            styles["ConnBody"],
        ),
        Spacer(1, 3 * mm),
    ]
    rows = [
        [
            "Levels",
            "Components",
            "Columns",
            "Beams",
            "Candidate nodes",
            "Beam ends checked",
            "Centreline matches",
            "Footprint only",
            "Unsupported",
            "Blockers",
        ]
    ]
    rows.append(
        [
            str(c[k])
            for k in (
                "levels",
                "components",
                "columns",
                "beams",
                "candidate_nodes",
                "beam_ends_checked",
                "beam_ends_column_centreline_matched",
                "beam_ends_column_footprint_only",
                "unsupported_beam_ends",
                "blockers",
            )
        ]
    )
    table = Table(
        rows,
        repeatRows=1,
        colWidths=[
            17 * mm,
            20 * mm,
            16 * mm,
            15 * mm,
            23 * mm,
            23 * mm,
            25 * mm,
            22 * mm,
            18 * mm,
            18 * mm,
        ],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.extend(
        [table, Spacer(1, 3 * mm), Paragraph("Issues requiring review", styles["Heading2"])]
    )
    issue_rows = [["Severity", "Code", "Floor", "Component", "Finding"]]
    for issue in result.get("issues", [])[:70]:
        issue_rows.append(
            [
                issue["severity"],
                issue["code"],
                str(issue.get("floor_id") or "-"),
                str(issue.get("component_id") or "-"),
                issue["message_ar"],
            ]
        )
    if len(issue_rows) == 1:
        issue_rows.append(
            [
                "INFO",
                "NO_GEOMETRIC_ISSUES",
                "-",
                "-",
                "No geometry blockers were detected by this limited preflight.",
            ]
        )
    it = Table(issue_rows, repeatRows=1, colWidths=[20 * mm, 45 * mm, 20 * mm, 34 * mm, 130 * mm])
    it.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6EE")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 6.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.extend(
        [
            it,
            Spacer(1, 3 * mm),
            Paragraph(
                "This is geometry/topology QA only. It does not establish FE suitability, diaphragm behavior, supports, loads, lateral stability, code compliance, member capacity, reinforcement or foundations.",
                styles["ConnBody"],
            ),
        ]
    )
    doc.build(story)


def create_connectivity_review_package(
    building_model: dict[str, Any], result: dict[str, Any]
) -> bytes:
    dxf = render_connectivity_dxf(building_model, result)
    from reportlab.pdfgen import canvas
    import tempfile

    with tempfile.TemporaryDirectory(prefix="connectivity_preflight_") as td:
        pdf_path = Path(td) / "building_connectivity_precheck.pdf"
        render_connectivity_report_pdf(result, pdf_path)
        files = {
            "building_stack_candidate.json": json.dumps(
                building_model, ensure_ascii=False, indent=2, allow_nan=False
            ).encode("utf-8"),
            "building_connectivity_precheck.json": json.dumps(
                result, ensure_ascii=False, indent=2, allow_nan=False
            ).encode("utf-8"),
            "building_connectivity_precheck.pdf": pdf_path.read_bytes(),
            "building_connectivity_precheck.dxf": dxf,
            "beam_end_connectivity.csv": _csv_bytes(
                result.get("beam_end_connectivity", []),
                ["floor_id", "beam_component_id", "end_index", "connection_type", "status"],
            ),
            "section_geometry_checks.csv": _csv_bytes(
                result.get("section_geometry_checks", []),
                ["floor_id", "component_id", "role", "status"],
            ),
            "issues.csv": _csv_bytes(
                result.get("issues", []),
                ["severity", "code", "floor_id", "component_id", "message_ar"],
            ),
            "README_AR.md": (
                "# تدقيق اتصال المبنى — Structural Studio\n\n"
                "هذه مرحلة فحص هندسي/طوبولوجي فقط. لا تنشئ نموذج عناصر منتهية الصلاحية للتحليل، ولا تحدد الديافرام/القيود/الأحمال.\n"
                "يجب تأكيد العناصر والاتصالات ومراجعة الوصلات اللامركزية والحوائط والفتحات قبل أي تحليل.\n"
                "ALL OUTPUTS ARE DRAFT / NOT FOR CONSTRUCTION.\n"
            ).encode("utf-8"),
        }
        files["manifest_sha256.json"] = json.dumps(
            {
                n: {"size_bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                for n, b in sorted(files.items())
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        out = BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in files.items():
                zf.writestr(name, data)
        with zipfile.ZipFile(BytesIO(out.getvalue())) as zf:
            bad = zf.testzip()
            if bad:
                raise RuntimeError(f"Invalid connectivity ZIP: {bad}")
            manifest = json.loads(zf.read("manifest_sha256.json"))
            for name, item in manifest.items():
                if hashlib.sha256(zf.read(name)).hexdigest() != item["sha256"]:
                    raise RuntimeError(f"Connectivity artifact hash mismatch: {name}")
        return out.getvalue()
