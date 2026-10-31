"""Markdown reports for design results. Every report opens with the status banner."""

from __future__ import annotations

from typing import Any

from .params import P, STATUS_BANNER


def _f(v, nd=1):
    return "-" if v is None else f"{v:.{nd}f}"


def _beam(r: dict[str, Any]) -> list[str]:
    inp = r["input"]
    out = [
        f"**Spans (m):** {inp['spans_m']}  |  **Section:** {inp['b_mm']:.0f} x {inp['h_mm']:.0f} mm"
        + (
            f" (T: bf={inp['flange']['bf_mm']:.0f}, tf={inp['flange']['tf_mm']:.0f})"
            if inp["flange"]
            else ""
        ),
        f"**fcu / fy / fyst:** {inp['fcu_MPa']} / {inp['fy_MPa']} / {inp['fyst_MPa']} MPa  |  "
        f"**Dead / Live (kN/m):** {inp['dead_kN_m']} / {inp['live_kN_m']}  |  self-weight {_f(inp['self_weight_kN_m'], 2)} kN/m",
        "",
        "### Sagging (mid-span)",
        "| Span | Mu (kN.m) | Bars | As prov (mm2) | Capacity | Util | d (mm) |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in r["spans"]:
        g = s["sagging"]
        out.append(
            f"| {s['index']} | {_f(g['Mu_kNm'])} | {g.get('bars') or g.get('reason', '-')} | {_f(g.get('As_prov_mm2'), 0)} "
            f"| {_f(g.get('capacity_kNm'))} | {_f(g.get('utilisation'), 2)} | {_f(g.get('d_mm'), 0)} |"
        )
    out += [
        "",
        "### Hogging (supports, top steel)",
        "| Support | Mu (kN.m) | Bars | Compression bars | Util | Basis |",
        "|---|---|---|---|---|---|",
    ]
    for s in r["supports"]:
        h = s["hogging"]
        out.append(
            f"| {s['index']} | {_f(h['Mu_kNm'])} | {h.get('bars') or h.get('reason', '-')} | {h.get('compression_bars') or '-'} "
            f"| {_f(h.get('utilisation'), 2)} | {h['basis']} |"
        )
    out += [
        "",
        "### Shear (stirrups)",
        "| Span | Zone | Vu (kN) | qu (MPa) | Stirrups |",
        "|---|---|---|---|---|",
    ]
    for s in r["spans"]:
        for z in s["shear"]["zones"]:
            st = (
                f"Φ{z['stirrup_dia_mm']:.0f}@{z['spacing_mm']:.0f} ({z['basis']})"
                if z["status"] == "OK"
                else z.get("reason")
            )
            out.append(
                f"| {s['index']} | {z['zone']} | {_f(z['Vu_kN'])} | {_f(z['qu_MPa'], 2)} | {st} |"
            )
    out += [
        "",
        f"**Ultimate support reactions (kN):** {[round(x, 1) for x in r['reactions']['ultimate_max_kN']]}",
    ]
    return out


def _slab(r: dict[str, Any]) -> list[str]:
    inp = r["input"]
    out = [
        f"**Spans (m):** {inp['spans_m']}  |  **Thickness:** {inp['thickness_mm']:.0f} mm  |  fcu/fy {inp['fcu_MPa']}/{inp['fy_MPa']} MPa",
        f"**Dead / Live (kN/m2):** {inp['dead_kN_m2']} / {inp['live_kN_m2']}  |  self-weight {_f(inp['self_weight_kN_m2'], 2)} kN/m2",
        "",
        "| Location | Mu (kN.m/m) | Bars | As prov (mm2/m) | Util |",
        "|---|---|---|---|---|",
    ]
    for s in r["spans"]:
        g = s["sagging"]
        out.append(
            f"| {g['location']} | {_f(g['Mu_kNm'])} | {g.get('bars') or g.get('reason')} | {_f(g.get('As_prov_mm2_per_m'), 0)} | {_f(g.get('utilisation'), 2)} |"
        )
    for s in r["supports"]:
        g = s["hogging"]
        out.append(
            f"| {g['location']} (top) | {_f(g['Mu_kNm'])} | {g.get('bars') or g.get('reason')} | {_f(g.get('As_prov_mm2_per_m'), 0)} | {_f(g.get('utilisation'), 2)} |"
        )
    out += [
        "",
        f"**Distribution steel:** {r['distribution_steel']['bars']}",
        "",
        "| Span | Vu (kN/m) | qu (MPa) | qcu (MPa) | |",
        "|---|---|---|---|---|",
    ]
    for s in r["shear"]:
        out.append(
            f"| {s['span']} | {_f(s['Vu_kN_per_m'])} | {_f(s['qu_MPa'], 2)} | {_f(s['qcu_MPa'], 2)} | {s['status']} |"
        )
    return out


def _column(r: dict[str, Any]) -> list[str]:
    inp, res = r["input"], r.get("result") or {}
    out = [
        f"**Section:** {inp['b_mm']} x {inp['h_mm']} mm  |  fcu/fy {inp.get('fcu_MPa', 30)}/{inp.get('fy_MPa', 400)} MPa",
        f"**Pu:** {_f(inp.get('Pu_kN'))} kN"
        + (f"  ({inp['Pu_source']})" if inp.get("Pu_source") else "")
        + f"  |  **Mux / Muy:** {inp.get('Mux_kNm', 0)} / {inp.get('Muy_kNm', 0)} kN.m",
    ]
    if r.get("slenderness"):
        s = r["slenderness"]
        out.append(
            f"**Slenderness:** lambda_x={_f(s['lambda_x'])}, lambda_y={_f(s['lambda_y'])} (limit {s['limit']}, {'braced' if s['braced'] else 'unbraced'})"
        )
    if res.get("nx"):
        out += [
            "",
            f"**Bars:** {res.get('bars') or f'{2*res['nx']+2*(res['ny']-2)}Φ{res['dia_mm']:.0f}'}  |  Ast {_f(res['Ast_mm2'], 0)} mm2  |  rho {res['rho']:.2%}",
        ]
        if res.get("tie_dia_mm"):
            out.append(f"**Ties:** Φ{res['tie_dia_mm']:.0f}@{res['tie_spacing_mm']:.0f}")
        out += [
            "",
            f"**Interaction ratio:** {_f(res.get('ratio'), 2)}  |  axial capacity {_f(res.get('P_cap_kN'), 0)} kN",
            "",
            "| Axis | M design | M capacity | e_min (mm) | e_min governs |",
            "|---|---|---|---|---|",
        ]
        for ax, d in (res.get("axes") or {}).items():
            out.append(
                f"| {ax} | {_f(d['M_design_kNm'])} | {_f(d['M_cap_kNm'])} | {_f(d['e_min_mm'], 0)} | {d['min_ecc_governs']} |"
            )
    return out


def _stirrups(d: dict[str, Any]) -> str:
    z = [x for sp in d["spans"] for x in sp["shear"]["zones"] if x["status"] == "OK"]
    if not z:
        return "-"
    tight = min(z, key=lambda x: x["spacing_mm"])
    loose = max(z, key=lambda x: x["spacing_mm"])
    a, b = (
        f"Φ{tight['stirrup_dia_mm']:.0f}@{tight['spacing_mm']:.0f}",
        f"Φ{loose['stirrup_dia_mm']:.0f}@{loose['spacing_mm']:.0f}",
    )
    return a if a == b else f"{a} .. {b}"


def _floor(r: dict[str, Any]) -> list[str]:
    inp, eq = r["input"], r["equilibrium"]
    out = [
        f"**Loads:** finishes {inp['finishes_kN_m2']} + live {inp['live_kN_m2']} kN/m2 (slab self weight added)  |  "
        f"storey height {inp['storey_height_m']} m  |  {inp['floors']} identical floors  |  "
        f"fcu/fy/fyst {inp['fcu_MPa']}/{inp['fy_MPa']}/{inp['fyst_MPa']} MPa",
        f"**Grid X (m):** {[round(x, 2) for x in r['layout']['grid_x_m']]}  |  **Grid Y (m):** {[round(y, 2) for y in r['layout']['grid_y_m']]}",
        "",
        f"**Load take-down check (dead):** applied {_f(eq['applied_dead_kN'])} kN, delivered to columns "
        f"{_f(eq['delivered_to_columns_dead_kN'])} kN (difference {eq['difference_pct']:.3f} %)",
        "",
        "## Column schedule",
        "| Column | x, y (m) | Section (mm) | Pu/floor (kN) | Pu total (kN) | Mux | Muy | Bars | Ties | Ratio | Status |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cid, c in r["columns"].items():
        d = c["design"].get("result") or {}
        out.append(
            f"| {cid} | {c['x']:.2f}, {c['y']:.2f} | {c['section_mm'][0]:.0f} x {c['section_mm'][1]:.0f} | {_f(c['Pu_per_floor_kN'], 0)} | {_f(c['Pu_kN'], 0)} "
            f"| {_f(c['Mux_kNm'])} | {_f(c['Muy_kNm'])} | {d.get('bars', '-')} | "
            + (f"Φ{d['tie_dia_mm']:.0f}@{d['tie_spacing_mm']:.0f}" if d.get("tie_dia_mm") else "-")
            + f" | {_f(d.get('ratio'), 2)} | {c['design']['status']} |"
        )
    out += [
        "",
        "## Beam schedule",
        "| Beam | Dir | Section (mm) | Spans (m) | Bottom bars per span | Top bars per support | Stirrups | Status |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for bid, b in r["beams"].items():
        d = b["design"]
        out.append(
            f"| {bid} | {b['axis']} @ {b['coord_m']:.2f} | {b['section_mm'][0]:.0f} x {b['section_mm'][1]:.0f} | "
            f"{[round(x, 2) for x in d['input']['spans_m']]} | "
            f"{' / '.join(str(s['sagging'].get('bars') or '-') for s in d['spans'])} | "
            f"{' / '.join(str(s['hogging'].get('bars') or '-') for s in d['supports'])} | {_stirrups(d)} | {d['status']} |"
        )
    out += [
        "",
        "## Slab schedule"
        + (
            " (strips by direction; CS = column strip, MS = middle strip, top steel at the two supports)"
            if r.get("system") in ("flat_plate", "flat_slab")
            else " (one-way strip in the short direction)"
        ),
        "| Panel | Size (m) | Thickness | Short dir / span case | Bottom | Top at supports | Distribution / M0 | Status |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for pid, s in r["slabs"].items():
        d = s["design"]
        if s.get("kind") == "flat_strips":
            for dr in ("x", "y"):
                e = d[dr]
                out.append(
                    f"| {pid} | {s['x1'] - s['x0']:.2f} x {s['y1'] - s['y0']:.2f} | {s['thickness_mm']:.0f} | {dr}: {e['case']} span | "
                    f"CS {e['bottom_cs'].get('bars') or '-'} / MS {e['bottom_ms'].get('bars') or '-'} | "
                    f"CS {e['top_start_cs'].get('bars') or '-'} , {e['top_end_cs'].get('bars') or '-'} / MS {e['top_start_ms'].get('bars') or '-'} , {e['top_end_ms'].get('bars') or '-'} | "
                    f"M0 {_f(e['M0'])} kN.m | {'OK' if all(e[k]['status'] == 'OK' for k in ('bottom_cs', 'bottom_ms', 'top_start_cs', 'top_end_cs', 'top_start_ms', 'top_end_ms')) else 'FAIL'} |"
                )
            continue
        if s.get("kind") == "rib":
            out.append(
                f"| {pid} | {s['x1'] - s['x0']:.2f} x {s['y1'] - s['y0']:.2f} | rib {s['thickness_mm']:.0f} | {s['direction']} | "
                f"{d['spans'][0]['sagging'].get('bars') or '-'} per rib | {' / '.join(str(x['hogging'].get('bars') or '-') for x in d['supports'])} | "
                f"{_stirrups(d)} | {d['status']} |"
            )
            continue
        out.append(
            f"| {pid} | {s['x1'] - s['x0']:.2f} x {s['y1'] - s['y0']:.2f} | {s['thickness_mm']:.0f} | {s['direction']} | "
            f"{d['spans'][0]['sagging'].get('bars') or '-'} | {' / '.join(str(x['hogging'].get('bars') or '-') for x in d['supports'])} | "
            f"{d['distribution_steel']['bars']} | {d['status']} |"
        )
    if r.get("system") in ("flat_plate", "flat_slab"):
        out += [
            "",
            "## Punching shear",
            "| Column | Position | Check | Vu (kN) | bo (mm) | d (mm) | beta | qu (MPa) | qcup (MPa) | Ratio | Status |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for cid, c in r["columns"].items():
            for where, k in c["punching"].items():
                out.append(
                    f"| {cid} | {k['position']} | {where} | {_f(k['Vu_kN'], 0)} | {_f(k['bo_mm'], 0)} | {_f(k['d_mm'], 0)} | {k['beta']} | "
                    f"{_f(k['qu_MPa'], 2)} | {_f(k['qcup_MPa'], 2)} | {_f(k['ratio'], 2)} | {k['status']} |"
                )
    out += ["", "# Calculation notes"]
    for bid, b in r["beams"].items():
        out += ["", f"## Beam {bid}", ""] + _beam(b["design"])
    for pid, s in r["slabs"].items():
        if s.get("kind") == "flat_strips":
            continue
        out += ["", f"## Slab panel {pid}", ""] + (
            _beam(s["design"]) if s.get("kind") == "rib" else _slab(s["design"])
        )
    for cid, c in r["columns"].items():
        out += ["", f"## Column {cid}", ""] + _column(c["design"])
    return out


def to_markdown(result: dict[str, Any]) -> str:
    kind = result["type"]
    lines = [f"# Design report - {result['name']} ({kind})", "", f"> **{STATUS_BANNER}**", ""]
    lines.append(
        f"**Status: {result['status']}**"
        + ("" if result["status"] == "OK" else " - " + "; ".join(result.get("failures") or []))
    )
    lines.append("")
    lines += {"continuous_beam": _beam, "slab_strip": _slab, "column": _column, "floor": _floor}[
        kind
    ](result)
    if result.get("warnings"):
        lines += ["", "### Warnings"] + [f"- {w}" for w in result["warnings"]]
    if result.get("assumptions"):
        lines += ["", "### Assumptions and limits"] + [f"- {a}" for a in result["assumptions"]]
    bad = P.unverified()
    lines += [
        "",
        "### Design-code parameters",
        f"{len(bad)} of {len(P.describe())} parameters are **unverified** against the official text. "
        "Compare each with the code edition in force (edit `structural_engine/design/params.py`).",
        "",
        "| Parameter | Value | Meaning |",
        "|---|---|---|",
    ]
    lines += [f"| {d['name']} | {d['value']} | {d['meaning']} |" for d in P.describe()]
    lines += ["", "*Generated by Structural Studio design engine. NOT FOR CONSTRUCTION.*", ""]
    return "\n".join(lines)
