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


def to_markdown(result: dict[str, Any]) -> str:
    kind = result["type"]
    lines = [f"# Design report - {result['name']} ({kind})", "", f"> **{STATUS_BANNER}**", ""]
    lines.append(
        f"**Status: {result['status']}**"
        + ("" if result["status"] == "OK" else " - " + "; ".join(result.get("failures") or []))
    )
    lines.append("")
    lines += {"continuous_beam": _beam, "slab_strip": _slab, "column": _column}[kind](result)
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
