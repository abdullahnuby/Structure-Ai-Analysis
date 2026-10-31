"""Verification checklist for the design-code parameters and the known formula-level deviations.

This module does NOT verify anything against ECP 203: the official text is not available to the
program. It records, for every parameter, what kind of number it is, how sure the author is that it
matches ECP 203, and what to compare. Regenerate the checklist with
    python -m structural_engine.design.verification > ECP_VERIFICATION_CHECKLIST_AR.md
"""

from __future__ import annotations

from .params import P

# name -> (kind, confidence, what to check). kind: code = should equal an ECP value; proposal = an
# engineering rule of thumb / default the engineer decides (no code value to find).
NOTES: dict[str, tuple[str, str, str]] = {
    "gamma_c": ("code", "high", "material factor, concrete"),
    "gamma_s": ("code", "high", "material factor, steel"),
    "concrete_stress_factor": ("code", "high", "design stress = 0.67 fcu/gamma_c (0.447 fcu)"),
    "stress_block_ratio": ("code", "high", "equivalent rectangular block depth a = 0.8 c"),
    "eps_cu": ("code", "high", "ultimate concrete strain"),
    "Es_MPa": ("code", "high", "steel modulus"),
    "Ec_factor": ("code", "medium", "Ec = 4400 sqrt(fcu)"),
    "unit_weight_concrete_kN_m3": ("code", "high", "RC unit weight (loads chapter, ECP 201)"),
    "load_factor_dead": ("code", "medium", "ultimate load combination 1.4 D + 1.6 L (check the edition in force)"),
    "load_factor_live": ("code", "medium", "ultimate load combination 1.4 D + 1.6 L (check the edition in force)"),
    "c_over_d_max": ("code", "medium", "ductility limit on neutral-axis depth; depends on fy"),
    "beam_min_steel_a": ("code", "medium", "As,min = 0.225 sqrt(fcu)/fy b d"),
    "beam_min_steel_b": ("code", "medium", "As,min >= 1.1/fy b d"),
    "min_steel_cap_factor": ("code", "medium", "As,min need not exceed 1.3 As,required"),
    "shear_qcu_factor": ("code", "medium", "beam concrete shear stress qcu = 0.24 sqrt(fcu/gamma_c)"),
    "shear_qu_max_factor": ("code", "medium", "max shear stress 0.7 sqrt(fcu/gamma_c); also check any absolute cap in MPa"),
    "stirrup_qcu_share": ("code", "medium", "qsu = qu - 0.5 qcu"),
    "stirrup_min_ratio": ("code", "medium", "minimum stirrups 0.4/fyst"),
    "stirrup_max_spacing_mm": ("code", "medium", "maximum stirrup spacing (also limited by depth/bar size)"),
    "stirrup_min_spacing_mm": ("proposal", "low", "practical minimum spacing"),
    "slab_qcu_factor": ("code", "low", "solid-slab shear stress"),
    "slab_min_steel_ratio": ("code", "low", "minimum slab steel depends on steel grade"),
    "slab_max_bar_spacing_mm": ("code", "medium", "maximum slab bar spacing"),
    "bar_diameters_mm": ("proposal", "high", "available bar sizes in the market"),
    "min_clear_spacing_mm": ("code", "medium", "minimum clear spacing between bars"),
    "column_axial_cap_ratio": ("code", "low", "see deviation 1: ECP uses 0.35 fcu Ac + 0.67 fy Asc"),
    "column_min_ecc_ratio": ("code", "medium", "minimum eccentricity 0.05 t"),
    "column_min_ecc_mm": ("code", "medium", "minimum eccentricity not less than 20 mm"),
    "column_min_steel_ratio": ("code", "low", "ECP states minimum steel against required / gross area; check the exact rule"),
    "column_max_steel_ratio": ("code", "low", "maximum longitudinal steel ratio"),
    "column_biaxial_alpha": ("code", "low", "ECP has its own biaxial-bending procedure; linear contour (1.0) is a conservative stand-in"),
    "column_slenderness_limit_braced": ("code", "medium", "short-column limit on slenderness ratio, braced"),
    "column_slenderness_limit_unbraced": ("code", "medium", "short-column limit on slenderness ratio, unbraced"),
    "column_tie_min_dia_mm": ("code", "medium", "minimum tie diameter"),
    "column_tie_dia_bar_ratio": ("code", "medium", "tie diameter >= 0.25 bar diameter"),
    "column_tie_max_spacing_mm": ("code", "medium", "maximum tie spacing"),
    "column_tie_spacing_bar_multiple": ("code", "medium", "tie spacing <= 15 bar diameters"),
    "grid_snap_tolerance_m": ("proposal", "high", "geometry tolerance of the layout proposal"),
    "max_beam_span_m": ("proposal", "high", "limit for proposing a beam between columns"),
    "slab_one_way_ratio": ("code", "medium", "long/short ratio separating one-way from two-way slabs"),
    "slab_thickness_span_ratio": ("proposal", "low", "rule of thumb; ECP gives span/depth ratios for deflection control"),
    "slab_min_thickness_mm": ("proposal", "high", "engineer's choice"),
    "beam_depth_span_ratio": ("proposal", "low", "rule of thumb; ECP gives span/depth ratios"),
    "beam_min_depth_mm": ("proposal", "high", "engineer's choice"),
    "beam_default_width_mm": ("proposal", "high", "engineer's choice"),
    "masonry_unit_weight_kN_m3": ("code", "medium", "wall unit weight (ECP 201 loads chapter)"),
    "rib_width_mm": ("proposal", "medium", "ECP/ block manufacturer limits on rib width"),
    "rib_spacing_mm": ("proposal", "medium", "ECP limits on rib spacing"),
    "rib_topping_mm": ("code", "low", "minimum topping thickness for ribbed slabs"),
    "rib_depth_span_ratio": ("proposal", "low", "rule of thumb"),
    "rib_min_depth_mm": ("proposal", "medium", "engineer's choice"),
    "rib_block_dead_kN_m2": ("proposal", "low", "depends on the block actually used"),
    "rib_bar_diameters_mm": ("proposal", "high", "available bar sizes"),
    "rib_stirrup_dia_mm": ("proposal", "medium", "engineer's choice"),
    "flat_plate_thickness_ratio": ("code", "low", "ECP flat-slab minimum thickness rules"),
    "flat_slab_thickness_ratio": ("code", "low", "ECP flat-slab minimum thickness rules"),
    "flat_plate_min_thickness_mm": ("code", "low", "ECP minimum flat-plate thickness"),
    "ddm_ext_neg": ("code", "low", "ACI-derived coefficient; check ECP flat-slab moment coefficients"),
    "ddm_ext_pos": ("code", "low", "ACI-derived coefficient; check ECP flat-slab moment coefficients"),
    "ddm_ext_int_neg": ("code", "low", "ACI-derived coefficient; check ECP flat-slab moment coefficients"),
    "ddm_int_neg": ("code", "low", "ACI-derived coefficient; check ECP flat-slab moment coefficients"),
    "ddm_int_pos": ("code", "low", "ACI-derived coefficient; check ECP flat-slab moment coefficients"),
    "ddm_cs_ext_neg": ("code", "low", "ACI-derived column-strip share; check ECP"),
    "ddm_cs_int_neg": ("code", "low", "ACI-derived column-strip share; check ECP"),
    "ddm_cs_pos": ("code", "low", "ACI-derived column-strip share; check ECP"),
    "ddm_unbalanced_coeff": ("code", "low", "ACI-derived unbalanced-moment coefficient"),
    "punching_qcup_factor": ("code", "low", "see deviation 2: ECP has additional limits"),
    "punching_beta_interior": ("code", "low", "ACI-style moment-transfer factor; ECP uses its own procedure"),
    "punching_beta_edge": ("code", "low", "ACI-style moment-transfer factor; ECP uses its own procedure"),
    "punching_beta_corner": ("code", "low", "ACI-style moment-transfer factor; ECP uses its own procedure"),
    "drop_panel_span_ratio": ("code", "low", "ECP drop-panel size rule"),
}

DEVIATIONS = [
    "Column axial capacity: the engine uses 0.8*(0.447 fcu (Ac-As) + fy/1.15 As) while ECP's short-column equation is 0.35 fcu Ac + 0.67 fy Asc. The engine's steel term is about 4 % higher (unconservative).",
    "Punching: only the first qcup limit (0.5 + short/long column side) is implemented. ECP/ACI also limit qcup through a d/bo term (large perimeters), which is missing and may be unconservative. Moment transfer uses ACI-style factors 1.15/1.3/1.5, not the ECP procedure.",
    "Flat plate / flat slab: moment coefficients, strip fractions, unbalanced-moment coefficient and minimum thicknesses come from the ACI direct design method; ECP 203's own flat-slab provisions (and the limits for using the method) were not applied.",
    "Slab load on beams: moment-equivalent uniform loads (w Ls/3 and w Ls/2 (1 - m^2/3)); compare with the ECP load-distribution coefficients, especially for shear.",
    "Beams: moments are taken at support centre-lines (no reduction to the support face); end hogging uses wu L^2/24 as a monolithic-frame minimum; no frame action, no pattern loading on columns.",
    "Ribs: no shear-strength increase for ribs and no solid zones; topping is not checked for local bending.",
    "Columns: effective-length factor k is an input (1.0 braced); second-order effects are not designed (slender columns are refused).",
    "Not implemented at all: deflection, crack width, development/lap lengths, curtailment, torsion, wind/seismic loads (ECP 201) and seismic detailing, foundations, stairs, cantilevers, punching reinforcement.",
]


def markdown() -> str:
    rows = {d["name"]: d for d in P.describe()}
    out = [
        "# قائمة مراجعة معاملات التصميم على ECP 203",
        "",
        "> **هذه القائمة لا تعني أن أي معامل اتراجع.** البرنامج لا يملك نص الكود الرسمي. كل خانة «ثقة» رأي كاتب الكود عن مدى تطابق القيمة مع ECP 203 (high/medium/low)، "
        "والمهندس هو اللي يقارن بالنسخة السارية ويضع القيمة المتحقَّق منها في ملف `STRUCTURAL_STUDIO_PARAMS` مع `_verified`.",
        "",
        "نوع المعامل: `code` = قيمة يجب أن تطابق الكود، `proposal` = قاعدة تقريبية/قرار مهندس (لا يوجد رقم كود يُبحث عنه).",
        "",
        "## الفروقات المعروفة على مستوى المعادلات",
        "",
    ]
    out += [f"{i}. {t}" for i, t in enumerate(DEVIATIONS, 1)]
    out += ["", "## المعاملات", "", "| Parameter | Value | Kind | Confidence | What to check | Verified |", "|---|---|---|---|---|---|"]
    for name in rows:
        kind, conf, note = NOTES[name]
        out.append(f"| {name} | {rows[name]['value']} | {kind} | {conf} | {note} | {'yes' if rows[name]['verified'] else 'NO'} |")
    low = [n for n, (k, c, _) in NOTES.items() if k == "code" and c == "low"]
    out += ["", f"**عدد معاملات `code` منخفضة الثقة: {len(low)}** — ابدأ بها (خصوصًا البلاطة المسطحة والاختراق).", ""]
    return "\n".join(out)


if __name__ == "__main__":
    print(markdown())
