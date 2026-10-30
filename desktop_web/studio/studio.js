"use strict";
/* Structural Studio — design workbench. All output is NOT FOR CONSTRUCTION. */

const KIND_LABEL = { continuous_beam: "كمرة مستمرة", slab_strip: "شريحة بلاطة", column: "عمود" };
const STORE_KEY = "structural-studio.elements.v1";

/* ---- field definitions ------------------------------------------------------------------- */
const F = (key, label, unit, opts = {}) => ({ key, label, unit, ...opts });
const COMMON = [
  F("fcu_MPa", "fcu", "MPa"),
  F("fy_MPa", "fy", "MPa"),
  F("cover_mm", "Cover", "mm"),
];
const FIELDS = {
  continuous_beam: [
    { group: "الهندسة" },
    F("spans_m", "Spans", "m — comma separated", { list: true, full: true }),
    F("b_mm", "b", "mm"), F("h_mm", "h", "mm"),
    F("support_width_mm", "Support width", "mm"),
    F("flange_width_mm", "Flange bf (T)", "mm — optional", { optional: true }),
    F("flange_thickness_mm", "Flange tf (T)", "mm — optional", { optional: true }),
    { group: "المواد والتغطية" },
    ...COMMON, F("fyst_MPa", "fy stirrups", "MPa"), F("stirrup_dia_mm", "Stirrup Φ", "mm"),
    { group: "الأحمال (بدون الوزن الذاتي)" },
    F("dead_kN_m", "Dead", "kN/m — one value or per span", { list: true, scalarOk: true }),
    F("live_kN_m", "Live", "kN/m — one value or per span", { list: true, scalarOk: true }),
    F("self_weight", "حساب الوزن الذاتي للقطاع", "", { bool: true, full: true }),
    F("end_fixity", "افتراض تثبيت جزئي عند الركائز الطرفية", "", { bool: true, full: true }),
  ],
  slab_strip: [
    { group: "الهندسة" },
    F("spans_m", "Spans", "m — comma separated", { list: true, full: true }),
    F("thickness_mm", "Thickness", "mm"), F("support_width_mm", "Support width", "mm"),
    { group: "المواد والتغطية" }, ...COMMON,
    { group: "الأحمال (بدون الوزن الذاتي)" },
    F("dead_kN_m2", "Dead (finishes)", "kN/m²"), F("live_kN_m2", "Live", "kN/m²"),
  ],
  column: [
    { group: "المقطع والمواد" },
    F("b_mm", "b", "mm"), F("h_mm", "h", "mm"), ...COMMON, F("tie_dia_mm", "Tie Φ", "mm"),
    { group: "الأحمال التصميمية (ultimate)" },
    F("Pu_kN", "Pu", "kN"), F("Mux_kNm", "Mux", "kN·m"), F("Muy_kNm", "Muy", "kN·m"),
    { group: "النحافة" },
    F("unsupported_length_m", "Unsupported length", "m"), F("k", "k", ""),
    F("braced", "إطار مثبّت جانبيًا (braced)", "", { bool: true, full: true }),
    { group: "فحص تسليح معيّن (اختياري — اتركه فارغًا ليُصمَّم)" },
    F("bars_nx", "nx", "bars", { optional: true }), F("bars_ny", "ny", "bars", { optional: true }),
    F("bars_dia", "Φ", "mm", { optional: true }),
  ],
};
const DEFAULTS = {
  continuous_beam: {
    type: "continuous_beam", name: "B1", spans_m: [5, 5, 5], b_mm: 250, h_mm: 600, fcu_MPa: 30,
    fy_MPa: 400, fyst_MPa: 280, cover_mm: 25, stirrup_dia_mm: 8, dead_kN_m: 12, live_kN_m: 8,
    self_weight: true, support_width_mm: 300, end_fixity: true,
  },
  slab_strip: {
    type: "slab_strip", name: "S1", spans_m: [4, 4], thickness_mm: 140, fcu_MPa: 30, fy_MPa: 400,
    cover_mm: 20, dead_kN_m2: 1.5, live_kN_m2: 2, support_width_mm: 250,
  },
  column: {
    type: "column", name: "C1", b_mm: 300, h_mm: 500, fcu_MPa: 30, fy_MPa: 400, cover_mm: 30,
    tie_dia_mm: 8, Pu_kN: 1500, Mux_kNm: 120, Muy_kNm: 30, unsupported_length_m: 3, k: 1, braced: true,
  },
};

/* ---- tiny DOM helpers ----------------------------------------------------------------------- */
const SVGNS = "http://www.w3.org/2000/svg";
function h(tag, attrs, ...kids) {
  const el = tag.startsWith("svg:") ? document.createElementNS(SVGNS, tag.slice(4)) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.setAttribute("class", v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const $ = (id) => document.getElementById(id);
const fmt = (v, d = 1) => (typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—");

/* ---- state / storage ----------------------------------------------------------------------- */
let elements = [];
let currentId = null;
let lastResult = null;
let debounce = null;
let runToken = 0;

function load() {
  try { elements = JSON.parse(localStorage.getItem(STORE_KEY) || "[]"); } catch (_) { elements = []; }
  if (!Array.isArray(elements)) elements = [];
}
function save() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(elements)); } catch (_) { /* private mode: stays in memory */ }
}
const current = () => elements.find((e) => e.id === currentId);
const uid = () => Math.random().toString(36).slice(2, 10);

function addElement(type, spec) {
  const base = spec || { ...DEFAULTS[type] };
  const n = elements.filter((e) => e.type === type).length + 1;
  if (!spec) base.name = `${{ continuous_beam: "B", slab_strip: "S", column: "C" }[type]}${n}`;
  const el = { id: uid(), type, spec: base, status: null };
  elements.push(el);
  save();
  select(el.id);
  run();
}

/* ---- sidebar ------------------------------------------------------------------------------- */
function renderList() {
  const ul = $("elements");
  ul.replaceChildren(
    ...elements.map((e) =>
      h("li", { class: e.id === currentId ? "active" : "", onclick: () => { select(e.id); run(); } },
        h("span", { class: `dot ${e.status === "OK" ? "ok" : e.status ? "fail" : ""}` }),
        h("span", { class: "nm" }, e.spec.name || "—"),
        h("span", { class: "ty" }, KIND_LABEL[e.type]))),
  );
  $("empty").classList.toggle("hidden", elements.length > 0);
  $("work").classList.toggle("hidden", elements.length === 0);
}

function select(id) {
  currentId = id;
  lastResult = null;
  const el = current();
  renderList();
  if (!el) return;
  $("kindLabel").textContent = KIND_LABEL[el.type];
  renderForm(el);
  $("result").replaceChildren(h("p", { class: "muted" }, "جاري التصميم…"));
}

/* ---- form ------------------------------------------------------------------------------- */
function valueToText(v) {
  if (Array.isArray(v)) return v.join(", ");
  return v === undefined || v === null ? "" : String(v);
}
function specToFormValue(spec, key) {
  if (key === "bars_nx") return spec.bars?.nx;
  if (key === "bars_ny") return spec.bars?.ny;
  if (key === "bars_dia") return spec.bars?.dia_mm;
  return spec[key];
}

function renderForm(el) {
  const form = $("form");
  const nodes = [
    h("label", { class: "f full" }, "اسم العنصر",
      h("input", { type: "text", class: "txt", name: "name", value: el.spec.name || "" })),
  ];
  for (const f of FIELDS[el.type]) {
    if (f.group) { nodes.push(h("div", { class: "grp" }, f.group)); continue; }
    const val = specToFormValue(el.spec, f.key);
    if (f.bool) {
      nodes.push(h("label", { class: "f chk full" },
        h("input", { type: "checkbox", name: f.key, checked: val !== false && val !== undefined ? true : false }), f.label));
      continue;
    }
    nodes.push(h("label", { class: `f${f.full ? " full" : ""}`, "data-key": f.key }, f.label,
      h("input", { type: "text", inputmode: "decimal", name: f.key, value: valueToText(val) }),
      f.unit ? h("span", { class: "u" }, f.unit) : null));
  }
  form.replaceChildren(...nodes);
}

function parseNumber(text) {
  const t = text.trim().replace(/[٠-٩]/g, (d) => "٠١٢٣٤٥٦٧٨٩".indexOf(d)).replace("٫", ".");
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : NaN;
}

/** Read the form into a spec; returns {spec, errors}. */
function readForm(el) {
  const spec = { type: el.type, name: $("form").elements.name.value.trim() || "element" };
  const errors = [];
  const bars = {};
  for (const f of FIELDS[el.type]) {
    if (f.group) continue;
    const input = $("form").elements[f.key];
    if (f.bool) { spec[f.key] = input.checked; continue; }
    const raw = input.value;
    let value;
    if (f.list) {
      const parts = raw.split(/[,\s،؛;]+/).filter(Boolean).map(parseNumber);
      if (parts.length === 0 || parts.some((p) => !Number.isFinite(p))) { errors.push(f.key); continue; }
      value = parts.length === 1 && f.scalarOk ? parts[0] : parts;
    } else {
      value = parseNumber(raw);
      if (value === null) {
        if (f.optional) continue;
        errors.push(f.key); continue;
      }
      if (Number.isNaN(value)) { errors.push(f.key); continue; }
    }
    if (f.key.startsWith("bars_")) bars[f.key.slice(5) === "dia" ? "dia_mm" : f.key.slice(5)] = value;
    else spec[f.key] = value;
  }
  const given = Object.keys(bars).length;
  if (given === 3) spec.bars = bars;
  else if (given > 0) errors.push("bars_nx", "bars_ny", "bars_dia");
  for (const lab of $("form").querySelectorAll("label.f[data-key]")) lab.classList.toggle("err", errors.includes(lab.dataset.key));
  return { spec, errors };
}

/* ---- run --------------------------------------------------------------------------------- */
async function run() {
  const el = current();
  if (!el) return;
  const { spec, errors } = readForm(el);
  const msg = $("formMsg");
  if (errors.length) {
    msg.textContent = "في حقول فاضية أو غير رقمية (معلّمة بالأحمر).";
    lastResult = null;
    $("result").replaceChildren(h("p", { class: "muted" }, "النتائج متوقفة لحد ما تتصحح المدخلات."));
    return;
  }
  const token = ++runToken;
  msg.textContent = "";
  el.spec = spec;
  try {
    const r = await fetch("/api/design", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(spec),
    });
    const data = await r.json().catch(() => ({}));
    if (token !== runToken) return;
    if (!r.ok) {
      msg.textContent = typeof data.detail === "string" ? data.detail : "المدخلات غير صالحة.";
      el.status = "FAIL";
      lastResult = null;
      $("result").replaceChildren(h("p", { class: "muted" }, "لا توجد نتائج — صحّح المدخلات."));
    } else {
      el.status = data.status;
      lastResult = data;
      try {
        renderResult(data, spec);
      } catch (err) {
        console.error(err);
        lastResult = null;
        $("result").replaceChildren(h("p", { class: "muted" }, "تعذّر عرض النتيجة."));
        msg.textContent = `خطأ في العرض: ${err.message}`;
      }
    }
  } catch (err) {
    console.error(err);
    msg.textContent = `خطأ: ${err && err.message ? err.message : "تعذّر الاتصال بالسيرفر المحلي."}`;
  }
  save();
  renderList();
}

/* ---- results ----------------------------------------------------------------------------- */
function statusChip(status) {
  const cls = status === "OK" ? "ok" : status === "SLENDER_NOT_DESIGNED" ? "warn" : "fail";
  const text = { OK: "OK — التصميم مكتمل", FAIL: "FAIL — لا يحقق", SLENDER_NOT_DESIGNED: "عمود نحيف — لم يُصمَّم" }[status] || status;
  return h("span", { class: `status ${cls}` }, text);
}
function util(u) {
  if (typeof u !== "number") return null;
  const cls = u > 1 ? "over" : u > 0.9 ? "hi" : "";
  return h("span", { class: `util ${cls}` }, h("i", { style: `width:${Math.min(100, u * 100)}%` }));
}
function table(head, rows) {
  return h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, head.map((t) => h("th", { class: t.num ? "num" : "" }, t.t || t)))),
    h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c) => (c && c.cell) ? c.cell : h("td", {}, c)))))));
}
const num = (v, d = 1) => ({ cell: h("td", { class: "num" }, fmt(v, d)) });
const barsCell = (s) => ({ cell: h("td", { class: "bars" }, s || "—") });
const utilCell = (u) => ({ cell: h("td", { class: "num" }, typeof u === "number" ? `${(u * 100).toFixed(0)}%` : "—", util(u)) });

function renderResult(r, spec) {
  const out = [h("div", {}, statusChip(r.status), " ", h("span", { class: "muted" }, r.name))];
  if (r.failures?.length) out.push(h("div", { class: "box bad" }, "أسباب عدم الاكتمال:", h("ul", {}, r.failures.map((f) => h("li", {}, f)))));
  if (r.type === "continuous_beam") out.push(...beamView(r));
  else if (r.type === "slab_strip") out.push(...slabView(r));
  else out.push(...columnView(r, spec));
  const notes = [...(r.warnings || []), ...(r.assumptions || [])];
  if (notes.length) {
    out.push(h("h3", {}, "افتراضات وحدود"));
    out.push(h("ul", { class: "assump" }, notes.map((n) => h("li", {}, n))));
  }
  out.push(h("p", { class: "muted" }, r.banner));
  out.push(h("details", {}, h("summary", {}, "JSON الكامل"), h("pre", {}, JSON.stringify(r, null, 2))));
  $("result").replaceChildren(...out);
}

function zoneRows(items, key) {
  return items.map((s) => {
    const z = s[key];
    return [z.location, num(z.Mu_kNm), barsCell(z.bars || (z.reason ? `✗ ${z.reason}` : "—")),
      num(z.As_prov_mm2 ?? z.As_prov_mm2_per_m, 0), num(z.capacity_kNm), utilCell(z.utilisation)];
  });
}
const ZONE_HEAD = ["Zone", { t: "Mu kN·m", num: true }, "Bars", { t: "As prov mm²", num: true }, { t: "φMn kN·m", num: true }, "Utilisation"];

function beamView(r) {
  const out = [];
  out.push(h("div", { class: "cards" },
    r.reactions.ultimate_max_kN.map((v, i) => h("div", { class: "card" }, h("b", {}, fmt(v, 1)), h("span", {}, `Ru max — support ${i} (kN)`)))));
  out.push(h("h3", {}, "التسليح — العزم الموجب (منتصف البحور)"));
  out.push(table(ZONE_HEAD, zoneRows(r.spans, "sagging")));
  out.push(h("h3", {}, "التسليح — العزم السالب (الركائز، حديد علوي)"));
  out.push(table(ZONE_HEAD, zoneRows(r.supports, "hogging")));
  out.push(h("h3", {}, "الكانات"));
  const rows = [];
  for (const s of r.spans) for (const z of s.shear.zones)
    rows.push([`span ${s.index} — ${z.zone}`, num(z.from_m, 2), num(z.to_m, 2), num(z.Vu_kN),
      barsCell(z.status === "OK" ? `${z.legs}L Φ${z.stirrup_dia_mm}@${z.spacing_mm}` : `✗ ${z.reason || z.status}`), z.basis || ""]);
  out.push(table(["Zone", { t: "from m", num: true }, { t: "to m", num: true }, { t: "Vu kN", num: true }, "Stirrups", "Basis"], rows));
  out.push(h("h3", {}, "غلاف العزوم والقص"));
  out.push(envelopeChart(r, "M"), envelopeChart(r, "V"));
  return out;
}

function slabView(r) {
  const out = [];
  out.push(h("h3", {}, "التسليح — العزم الموجب (لكل متر عرض)"));
  out.push(table(ZONE_HEAD.map((t) => (t === "As prov mm²" ? { t: "As mm²/m", num: true } : t)), zoneRows(r.spans, "sagging")));
  out.push(h("h3", {}, "التسليح — العزم السالب (حديد علوي)"));
  out.push(table(ZONE_HEAD.map((t) => (t === "As prov mm²" ? { t: "As mm²/m", num: true } : t)), zoneRows(r.supports, "hogging")));
  out.push(h("div", { class: "cards" },
    h("div", { class: "card" }, h("b", {}, r.distribution_steel.bars), h("span", {}, "حديد التوزيع (عمودي على الرئيسي)"))));
  out.push(h("h3", {}, "القص (خرسانة فقط)"));
  out.push(table(["Span", { t: "Vu kN/m", num: true }, { t: "qu MPa", num: true }, { t: "qcu MPa", num: true }, "Status"],
    r.shear.map((s) => [s.span, num(s.Vu_kN_per_m), num(s.qu_MPa, 3), num(s.qcu_MPa, 3), s.status])));
  return out;
}

function columnView(r, spec) {
  const out = [];
  const s = r.slenderness;
  if (s) out.push(h("div", { class: "cards" },
    h("div", { class: "card" }, h("b", {}, `${fmt(s.lambda_x, 1)} / ${fmt(s.lambda_y, 1)}`), h("span", {}, `λx / λy — limit ${s.limit}`))));
  const res = r.result;
  if (!res || !res.axes || typeof res.ratio !== "number") {
    out.push(h("p", { class: "muted" }, "لا يوجد تسليح مقترح يحقق الاشتراطات — راجع الأسباب أعلاه."));
    return out;
  }
  out.push(h("div", { class: "cards" },
    h("div", { class: "card" }, h("b", {}, res.bars), h("span", {}, "Longitudinal bars")),
    h("div", { class: "card" }, h("b", {}, `Φ${res.tie_dia_mm}@${res.tie_spacing_mm}`), h("span", {}, "Ties")),
    h("div", { class: "card" }, h("b", {}, `${(res.ratio * 100).toFixed(0)}%`), h("span", {}, "Biaxial ratio (≤ 100%)")),
    h("div", { class: "card" }, h("b", {}, `${(res.rho * 100).toFixed(2)}%`), h("span", {}, `ρ — As ${fmt(res.Ast_mm2, 0)} mm²`)),
    h("div", { class: "card" }, h("b", {}, fmt(res.P_cap_kN, 0)), h("span", {}, "Axial cap. kN (e = 0)"))));
  out.push(h("h3", {}, "المحاور"));
  out.push(table(["Axis", { t: "M design kN·m", num: true }, { t: "M cap kN·m", num: true }, { t: "e min mm", num: true }, "Min ecc. governs"],
    ["x", "y"].map((a) => [a, num(res.axes[a].M_design_kNm), num(res.axes[a].M_cap_kNm), num(res.axes[a].e_min_mm, 0), res.axes[a].min_ecc_governs ? "نعم" : "لا"])));
  out.push(h("h3", {}, "القطاع"), sectionChart(res, spec));
  return out;
}

/* ---- charts ------------------------------------------------------------------------------- */
function sectionChart(res, spec) {
  const b = spec.b_mm, hh = spec.h_mm, scale = 200 / Math.max(b, hh);
  const W = b * scale, H = hh * scale, pad = 50;
  const edge = (spec.cover_mm || 30) + res.tie_dia_mm + res.dia_mm / 2;
  const pts = [];
  const row = (n, y) => { for (let i = 0; i < n; i++) pts.push([edge + (n === 1 ? (b - 2 * edge) / 2 : (i * (b - 2 * edge)) / (n - 1)), y]); };
  row(res.nx, edge); row(res.nx, hh - edge);
  const side = res.ny - 2;
  for (let j = 1; j <= side; j++) { const y = edge + (j * (hh - 2 * edge)) / (side + 1); pts.push([edge, y], [b - edge, y]); }
  const svg = h("svg:svg", { class: "chart", viewBox: `0 0 ${W + pad * 2} ${H + pad * 2}`, style: `max-width:${W + pad * 2 + 80}px`, role: "img", "aria-label": "Column section" },
    h("svg:rect", { x: pad, y: pad, width: W, height: H, fill: "none", stroke: "var(--ink)", "stroke-width": 1.5 }),
    h("svg:rect", { x: pad + (spec.cover_mm || 30) * scale, y: pad + (spec.cover_mm || 30) * scale, width: W - 2 * (spec.cover_mm || 30) * scale, height: H - 2 * (spec.cover_mm || 30) * scale, fill: "none", stroke: "var(--muted)", "stroke-dasharray": "4 3" }),
    ...pts.map(([x, y]) => h("svg:circle", { cx: pad + x * scale, cy: pad + y * scale, r: Math.max(3, (res.dia_mm / 2) * scale), fill: "var(--c2)" })),
    h("svg:text", { x: pad + W / 2, y: pad - 6, "text-anchor": "middle" }, `b = ${b}`),
    h("svg:text", { x: pad - 6, y: pad + H / 2, "text-anchor": "end" }, `h = ${hh}`));
  return svg;
}

function envelopeChart(r, mode) {
  const env = r.envelope, W = 760, Hc = 190, padL = 46, padR = 14, padT = 22, padB = 20;
  const lengths = r.spans.map((s) => s.length_m);
  const total = lengths.reduce((a, b) => a + b, 0);
  const offs = lengths.map((_, i) => lengths.slice(0, i).reduce((a, b) => a + b, 0));
  const upKey = mode === "M" ? "M_max_kNm" : "V_max_kN", loKey = mode === "M" ? "M_min_kNm" : "V_min_kN";
  const all = env[upKey].flat().concat(env[loKey].flat());
  let lo = Math.min(0, ...all), hi = Math.max(0, ...all);
  if (hi - lo < 1e-9) hi = lo + 1;
  const sx = (x) => padL + (x / total) * (W - padL - padR);
  // bending moment is drawn with sagging below the axis (engineering convention); shear upward positive
  const sy = (v) => padT + (mode === "M" ? (v - lo) / (hi - lo) : (hi - v) / (hi - lo)) * (Hc - padT - padB);
  const y0 = sy(0);
  const kids = [h("svg:line", { x1: padL, x2: W - padR, y1: y0, y2: y0, stroke: "var(--muted)" })];
  lengths.forEach((_, i) => {
    const xs = env.x_m[i].map((x) => x + offs[i]);
    const top = xs.map((x, k) => [sx(x), sy(env[upKey][i][k])]);
    const bot = xs.map((x, k) => [sx(x), sy(env[loKey][i][k])]).reverse();
    const pts = (a) => a.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
    kids.push(h("svg:polygon", { points: pts(top.concat(bot)), fill: "var(--fill)", stroke: "none" }));
    kids.push(h("svg:polyline", { points: pts(top), fill: "none", stroke: "var(--c1)", "stroke-width": 1.6 }));
    kids.push(h("svg:polyline", { points: pts(bot.slice().reverse()), fill: "none", stroke: "var(--c2)", "stroke-width": 1.6 }));
    const mx = Math.max(...env[upKey][i]);
    const k = env[upKey][i].indexOf(mx);
    if (mode === "M" || Math.abs(mx) > 0) kids.push(h("svg:text", { x: sx(xs[k]), y: sy(mx) + (mode === "M" ? 12 : -4), "text-anchor": "middle" }, fmt(mx, 1)));
  });
  [0, ...lengths.map((_, i) => offs[i] + lengths[i])].forEach((x, i) => {
    kids.push(h("svg:path", { d: `M${sx(x)} ${Hc - padB + 2} l-5 9 h10 z`, fill: "var(--ink)" }));
    const idx = Math.min(i, r.spans.length - 1), loV = i === 0 ? env[loKey][0][0] : env[loKey][Math.min(i - 1, r.spans.length - 1)].at(-1);
    if (mode === "M" && loV < -0.01) kids.push(h("svg:text", { x: sx(x), y: sy(loV) - 5, "text-anchor": "middle" }, fmt(loV, 1)));
  });
  kids.push(h("svg:text", { x: 4, y: 14 }, mode === "M" ? "M kN·m (موجب لأسفل)" : "V kN"));
  return h("svg:svg", { class: "chart", viewBox: `0 0 ${W} ${Hc + 10}`, role: "img", "aria-label": mode === "M" ? "Moment envelope" : "Shear envelope" }, ...kids);
}

/* ---- downloads ---------------------------------------------------------------------------- */
function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = h("a", { href: url, download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
const safeName = () => (current()?.spec.name || "design").replace(/[^\w\-]+/g, "_");

async function downloadReport() {
  const el = current();
  if (!el) return;
  const { spec, errors } = readForm(el);
  if (errors.length) { $("formMsg").textContent = "صحّح المدخلات أولًا."; return; }
  const r = await fetch("/api/design?report=true", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(spec) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { $("formMsg").textContent = "تعذّر إنشاء التقرير."; return; }
  download(`${safeName()}.md`, data.report_markdown, "text/markdown;charset=utf-8");
}

/* ---- params dialog ---------------------------------------------------------------------- */
async function showParams() {
  const dlg = $("paramsDialog");
  try {
    const p = await (await fetch("/api/design/params")).json();
    $("paramsNote").textContent = p.banner;
    $("paramsTable").replaceChildren(
      h("thead", {}, h("tr", {}, h("th", {}, "Parameter"), h("th", { class: "num" }, "Value"), h("th", {}, "المعنى"), h("th", {}, "الحالة"))),
      h("tbody", {}, p.parameters.map((x) => h("tr", {}, h("td", {}, x.name), h("td", { class: "num" }, String(x.value)), h("td", {}, x.meaning), h("td", {}, x.verified ? "متحقَّق" : "غير متحقَّق")))));
  } catch (_) { $("paramsNote").textContent = "تعذّر تحميل المعاملات."; }
  dlg.showModal();
}

async function loadBanner() {
  try {
    const p = await (await fetch("/api/design/params")).json();
    $("banner").textContent = `${p.banner} (${p.unverified} معامل غير متحقَّق)`;
  } catch (_) { $("banner").textContent = "UNVERIFIED — كل النتائج غير صالحة للتنفيذ."; }
}

/* ---- wiring ------------------------------------------------------------------------------- */
function wire() {
  document.querySelectorAll("[data-add]").forEach((b) => b.addEventListener("click", () => addElement(b.dataset.add)));
  document.querySelectorAll("[data-example]").forEach((b) => b.addEventListener("click", () => addElement(b.dataset.example)));
  $("runBtn").addEventListener("click", run);
  $("form").addEventListener("input", () => {
    if (!$("autoRun").checked) return;
    clearTimeout(debounce);
    debounce = setTimeout(run, 500);
  });
  $("form").addEventListener("submit", (e) => e.preventDefault());
  $("deleteBtn").addEventListener("click", () => {
    const el = current();
    if (!el || !confirm(`حذف ${el.spec.name}؟`)) return;
    elements = elements.filter((x) => x.id !== el.id);
    save();
    currentId = elements[0]?.id || null;
    renderList();
    if (currentId) { select(currentId); run(); }
  });
  $("dlReport").addEventListener("click", downloadReport);
  $("dlJson").addEventListener("click", () => lastResult && download(`${safeName()}.json`, JSON.stringify(lastResult, null, 2), "application/json"));
  $("exportAll").addEventListener("click", () => download("structural-studio-elements.json", JSON.stringify(elements.map(({ type, spec }) => ({ type, spec })), null, 2), "application/json"));
  $("importFile").addEventListener("change", async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    try {
      const data = JSON.parse(await f.text());
      const items = (Array.isArray(data) ? data : [data]).map((x) => (x.spec ? x : { type: x.type, spec: x }));
      let added = 0;
      for (const it of items) {
        if (!KIND_LABEL[it.type] || typeof it.spec !== "object") continue;
        elements.push({ id: uid(), type: it.type, spec: { ...it.spec, type: it.type }, status: null });
        added++;
      }
      save();
      if (added) { select(elements.at(-1).id); run(); } else $("formMsg").textContent = "الملف لا يحتوي عناصر صالحة.";
    } catch (_) { alert("ملف JSON غير صالح."); }
    e.target.value = "";
  });
  $("showParams").addEventListener("click", showParams);
  $("closeParams").addEventListener("click", () => $("paramsDialog").close());
}

load();
wire();
loadBanner();
renderList();
if (elements.length) { select(elements[0].id); run(); }
