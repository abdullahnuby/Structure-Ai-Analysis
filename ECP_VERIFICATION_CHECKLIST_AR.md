# قائمة مراجعة معاملات التصميم على ECP 203

> **هذه القائمة لا تعني أن أي معامل اتراجع.** البرنامج لا يملك نص الكود الرسمي. كل خانة «ثقة» رأي كاتب الكود عن مدى تطابق القيمة مع ECP 203 (high/medium/low)، والمهندس هو اللي يقارن بالنسخة السارية ويضع القيمة المتحقَّق منها في ملف `STRUCTURAL_STUDIO_PARAMS` مع `_verified`.

نوع المعامل: `code` = قيمة يجب أن تطابق الكود، `proposal` = قاعدة تقريبية/قرار مهندس (لا يوجد رقم كود يُبحث عنه).

## الفروقات المعروفة على مستوى المعادلات

1. Column axial capacity: the engine uses 0.8*(0.447 fcu (Ac-As) + fy/1.15 As) while ECP's short-column equation is 0.35 fcu Ac + 0.67 fy Asc. The engine's steel term is about 4 % higher (unconservative).
2. Punching: only the first qcup limit (0.5 + short/long column side) is implemented. ECP/ACI also limit qcup through a d/bo term (large perimeters), which is missing and may be unconservative. Moment transfer uses ACI-style factors 1.15/1.3/1.5, not the ECP procedure.
3. Flat plate / flat slab: moment coefficients, strip fractions, unbalanced-moment coefficient and minimum thicknesses come from the ACI direct design method; ECP 203's own flat-slab provisions (and the limits for using the method) were not applied.
4. Slab load on beams: moment-equivalent uniform loads (w Ls/3 and w Ls/2 (1 - m^2/3)); compare with the ECP load-distribution coefficients, especially for shear.
5. Beams: moments are taken at support centre-lines (no reduction to the support face); end hogging uses wu L^2/24 as a monolithic-frame minimum; no frame action, no pattern loading on columns.
6. Ribs: no shear-strength increase for ribs and no solid zones; topping is not checked for local bending.
7. Columns: effective-length factor k is an input (1.0 braced); second-order effects are not designed (slender columns are refused).
8. Not implemented at all: deflection, crack width, development/lap lengths, curtailment, torsion, wind/seismic loads (ECP 201) and seismic detailing, foundations, stairs, cantilevers, punching reinforcement.

## المعاملات

| Parameter | Value | Kind | Confidence | What to check | Verified |
|---|---|---|---|---|---|
| gamma_c | 1.5 | code | high | material factor, concrete | NO |
| gamma_s | 1.15 | code | high | material factor, steel | NO |
| concrete_stress_factor | 0.67 | code | high | design stress = 0.67 fcu/gamma_c (0.447 fcu) | NO |
| stress_block_ratio | 0.8 | code | high | equivalent rectangular block depth a = 0.8 c | NO |
| eps_cu | 0.003 | code | high | ultimate concrete strain | NO |
| Es_MPa | 200000.0 | code | high | steel modulus | NO |
| Ec_factor | 4400.0 | code | medium | Ec = 4400 sqrt(fcu) | NO |
| unit_weight_concrete_kN_m3 | 25.0 | code | high | RC unit weight (loads chapter, ECP 201) | NO |
| load_factor_dead | 1.4 | code | medium | ultimate load combination 1.4 D + 1.6 L (check the edition in force) | NO |
| load_factor_live | 1.6 | code | medium | ultimate load combination 1.4 D + 1.6 L (check the edition in force) | NO |
| c_over_d_max | 0.45 | code | medium | ductility limit on neutral-axis depth; depends on fy | NO |
| beam_min_steel_a | 0.225 | code | medium | As,min = 0.225 sqrt(fcu)/fy b d | NO |
| beam_min_steel_b | 1.1 | code | medium | As,min >= 1.1/fy b d | NO |
| min_steel_cap_factor | 1.3 | code | medium | As,min need not exceed 1.3 As,required | NO |
| shear_qcu_factor | 0.24 | code | medium | beam concrete shear stress qcu = 0.24 sqrt(fcu/gamma_c) | NO |
| shear_qu_max_factor | 0.7 | code | medium | max shear stress 0.7 sqrt(fcu/gamma_c); also check any absolute cap in MPa | NO |
| stirrup_qcu_share | 0.5 | code | medium | qsu = qu - 0.5 qcu | NO |
| stirrup_min_ratio | 0.4 | code | medium | minimum stirrups 0.4/fyst | NO |
| stirrup_max_spacing_mm | 200.0 | code | medium | maximum stirrup spacing (also limited by depth/bar size) | NO |
| stirrup_min_spacing_mm | 75.0 | proposal | low | practical minimum spacing | NO |
| slab_qcu_factor | 0.16 | code | low | solid-slab shear stress | NO |
| slab_min_steel_ratio | 0.0015 | code | low | minimum slab steel depends on steel grade | NO |
| slab_max_bar_spacing_mm | 200.0 | code | medium | maximum slab bar spacing | NO |
| bar_diameters_mm | [12, 16, 18, 20, 22, 25, 28, 32] | proposal | high | available bar sizes in the market | NO |
| min_clear_spacing_mm | 25.0 | code | medium | minimum clear spacing between bars | NO |
| column_axial_cap_ratio | 0.8 | code | low | see deviation 1: ECP uses 0.35 fcu Ac + 0.67 fy Asc | NO |
| column_min_ecc_ratio | 0.05 | code | medium | minimum eccentricity 0.05 t | NO |
| column_min_ecc_mm | 20.0 | code | medium | minimum eccentricity not less than 20 mm | NO |
| column_min_steel_ratio | 0.008 | code | low | ECP states minimum steel against required / gross area; check the exact rule | NO |
| column_max_steel_ratio | 0.04 | code | low | maximum longitudinal steel ratio | NO |
| column_biaxial_alpha | 1.0 | code | low | ECP has its own biaxial-bending procedure; linear contour (1.0) is a conservative stand-in | NO |
| column_slenderness_limit_braced | 15.0 | code | medium | short-column limit on slenderness ratio, braced | NO |
| column_slenderness_limit_unbraced | 10.0 | code | medium | short-column limit on slenderness ratio, unbraced | NO |
| column_tie_min_dia_mm | 8.0 | code | medium | minimum tie diameter | NO |
| column_tie_dia_bar_ratio | 0.25 | code | medium | tie diameter >= 0.25 bar diameter | NO |
| column_tie_max_spacing_mm | 200.0 | code | medium | maximum tie spacing | NO |
| column_tie_spacing_bar_multiple | 15.0 | code | medium | tie spacing <= 15 bar diameters | NO |
| grid_snap_tolerance_m | 0.15 | proposal | high | geometry tolerance of the layout proposal | NO |
| max_beam_span_m | 8.0 | proposal | high | limit for proposing a beam between columns | NO |
| slab_one_way_ratio | 2.0 | code | medium | long/short ratio separating one-way from two-way slabs | NO |
| slab_thickness_span_ratio | 32.0 | proposal | low | rule of thumb; ECP gives span/depth ratios for deflection control | NO |
| slab_min_thickness_mm | 120.0 | proposal | high | engineer's choice | NO |
| beam_depth_span_ratio | 12.0 | proposal | low | rule of thumb; ECP gives span/depth ratios | NO |
| beam_min_depth_mm | 500.0 | proposal | high | engineer's choice | NO |
| beam_default_width_mm | 250.0 | proposal | high | engineer's choice | NO |
| masonry_unit_weight_kN_m3 | 18.0 | code | medium | wall unit weight (ECP 201 loads chapter) | NO |
| rib_width_mm | 150.0 | proposal | medium | ECP/ block manufacturer limits on rib width | NO |
| rib_spacing_mm | 500.0 | proposal | medium | ECP limits on rib spacing | NO |
| rib_topping_mm | 70.0 | code | low | minimum topping thickness for ribbed slabs | NO |
| rib_depth_span_ratio | 20.0 | proposal | low | rule of thumb | NO |
| rib_min_depth_mm | 200.0 | proposal | medium | engineer's choice | NO |
| rib_block_dead_kN_m2 | 1.0 | proposal | low | depends on the block actually used | NO |
| rib_bar_diameters_mm | [10, 12, 14, 16, 18] | proposal | high | available bar sizes | NO |
| rib_stirrup_dia_mm | 6.0 | proposal | medium | engineer's choice | NO |
| flat_plate_thickness_ratio | 30.0 | code | low | ECP flat-slab minimum thickness rules | NO |
| flat_slab_thickness_ratio | 33.0 | code | low | ECP flat-slab minimum thickness rules | NO |
| flat_plate_min_thickness_mm | 180.0 | code | low | ECP minimum flat-plate thickness | NO |
| ddm_ext_neg | 0.26 | code | low | ACI-derived coefficient; check ECP flat-slab moment coefficients | NO |
| ddm_ext_pos | 0.52 | code | low | ACI-derived coefficient; check ECP flat-slab moment coefficients | NO |
| ddm_ext_int_neg | 0.7 | code | low | ACI-derived coefficient; check ECP flat-slab moment coefficients | NO |
| ddm_int_neg | 0.65 | code | low | ACI-derived coefficient; check ECP flat-slab moment coefficients | NO |
| ddm_int_pos | 0.35 | code | low | ACI-derived coefficient; check ECP flat-slab moment coefficients | NO |
| ddm_cs_ext_neg | 1.0 | code | low | ACI-derived column-strip share; check ECP | NO |
| ddm_cs_int_neg | 0.75 | code | low | ACI-derived column-strip share; check ECP | NO |
| ddm_cs_pos | 0.6 | code | low | ACI-derived column-strip share; check ECP | NO |
| ddm_unbalanced_coeff | 0.07 | code | low | ACI-derived unbalanced-moment coefficient | NO |
| punching_qcup_factor | 0.316 | code | low | see deviation 2: ECP has additional limits | NO |
| punching_beta_interior | 1.15 | code | low | ACI-style moment-transfer factor; ECP uses its own procedure | NO |
| punching_beta_edge | 1.3 | code | low | ACI-style moment-transfer factor; ECP uses its own procedure | NO |
| punching_beta_corner | 1.5 | code | low | ACI-style moment-transfer factor; ECP uses its own procedure | NO |
| drop_panel_span_ratio | 3.0 | code | low | ECP drop-panel size rule | NO |

**عدد معاملات `code` منخفضة الثقة: 24** — ابدأ بها (خصوصًا البلاطة المسطحة والاختراق).

