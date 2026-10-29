from __future__ import annotations

"""Structural Studio — simplified guided workspace (Arabic-first UI).

This replaces the old tab-dense interface with a five-screen, review-first workflow.
Engineering engines remain separate modules. All generated models are drafts only.
"""
import json
import hashlib
from pathlib import Path
from typing import Any

import streamlit as st

from structural_engine.ai_copilot import OllamaClient, OllamaUnavailable
from structural_engine.dxf_inspector import inspect_dxf_bytes
from structural_engine.dxf_structural_inference import analyze_dxf_structure
from structural_engine.building_stack import (
    make_architectural_plan_candidate,
    build_multistorey_building_candidate,
    render_building_stack_preview_png,
    create_building_stack_review_package,
)
from structural_engine.engineering_agent import EngineeringAgent, build_engineering_tools

ROOT = Path(__file__).resolve().parent

st.set_page_config(page_title="Structural Studio | مهندس المبنى", page_icon="🏗️", layout="wide", initial_sidebar_state="collapsed")

st.markdown(r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800&display=swap');
:root { --ink:#172B4D; --muted:#68788A; --line:#E1E8F0; --primary:#176B87; --primary2:#0F536A; --soft:#F3F8FB; --good:#16794B; --warn:#9A6700; }
html, body, [class*="css"], [data-testid="stAppViewContainer"] { direction:rtl; font-family:'Cairo',sans-serif; }
[data-testid="stSidebar"] { display:none; }
.block-container { max-width: 1240px; padding-top:1.25rem; padding-bottom:3rem; }
[data-testid="stMarkdownContainer"] { text-align:right; }
[data-testid="stWidgetLabel"] p, label, .stAlert { text-align:right; }
.hero { background:linear-gradient(120deg,#123B53 0%,#176B87 65%,#31889A 100%); color:white; border-radius:22px; padding:30px 34px; margin-bottom:18px; box-shadow:0 10px 28px rgba(20,66,91,.12); }
.hero h1 { color:white; font-size:2rem; margin:0 0 8px 0; font-weight:800; }
.hero p { color:#E7F5F8; margin:0; font-size:1.03rem; }
.section-title { font-size:1.35rem; color:var(--ink); font-weight:800; margin:.25rem 0 .2rem; }
.section-subtitle { color:var(--muted); margin-bottom:1.2rem; }
.step-card { background:white; border:1px solid var(--line); border-radius:16px; padding:18px 19px; min-height:126px; }
.step-no { display:inline-flex; width:34px; height:34px; border-radius:11px; align-items:center; justify-content:center; background:#E7F3F7; color:var(--primary2); font-weight:800; margin-bottom:10px; }
.status-line { background:#F4F8FA; border:1px solid var(--line); border-radius:13px; padding:12px 16px; color:var(--ink); }
.step-chip { border:1px solid var(--line); background:#F8FAFC; border-radius:12px; padding:10px 8px; min-height:58px; text-align:center; color:var(--muted); font-size:.88rem; font-weight:700; }
.step-chip.active { background:#EAF5F8; color:#0F536A; border:1px solid #78B8C9; box-shadow:inset 0 0 0 1px #C8E5EC; }
.step-chip.done { background:#EFF8F2; color:#176B45; border-color:#B5DDC4; }
.cta-panel { background:#F3F8FB; border:1px solid #DCEAF0; border-radius:18px; padding:22px 24px; }
.cta-panel h3 { color:var(--ink); margin:0 0 6px 0; }
div.stButton > button { border-radius:11px; min-height:2.7rem; font-weight:700; }
div[data-testid="stDownloadButton"] button { border-radius:11px; font-weight:700; }
[data-testid="stFileUploader"] { border:1px dashed #B9CBD6; border-radius:13px; padding:9px; background:#FBFDFE; }
[data-testid="stForm"] { border:1px solid var(--line); border-radius:15px; padding:18px; }
hr { border-color:var(--line); }
.small-muted { color:var(--muted); font-size:.9rem; }
.pill { background:#E6F5EC; color:#11643D; border-radius:99px; padding:4px 10px; font-weight:700; font-size:.85rem; display:inline-block; }
.draft-warning { background:#FFF7E6; border:1px solid #F2D69B; color:#805B0B; border-radius:12px; padding:11px 15px; margin:10px 0 16px; }
</style>
""", unsafe_allow_html=True)

# -------------------- State --------------------
def _init(key: str, value: Any) -> None:
    if key not in st.session_state:
        st.session_state[key] = value

_init("screen", "home")
_init("project", {
    "name":"", "number":"", "location":"", "use":"سكني", "code":"",
    "fc":30.0, "fy":420.0, "soil_status":"غير متوفر", "soil_notes":"",
    "live_load_basis":"", "wind_basis":"", "seismic_basis":"", "groundwater":"",
})
_init("plan_uploads", {k: None for k in ("ground", "typical", "basement", "roof")})
_init("plan_candidates", {})
_init("plan_analyses", {})
_init("plan_summaries", {})
_init("plans_units", "مم")
_init("plans_units_confirmed", False)
_init("plans_layers_confirmed", False)
_init("plans_reviewed", False)
_init("building_config", None)
_init("building_model", None)
_init("building_preview", None)
_init("building_package", None)
_init("ai_models", [])
_init("ai_model_check_done", False)
_init("ai_connection_error", None)
_init("ai_selected_model", "")
_init("ai_tested_model", "")
_init("ai_test_ok", False)
_init("ai_test_result", "")
_init("ai_test_error", "")
_init("chat_history", [])
_init("agent_traces", [])
_init("latest_agent_result", None)

SCREEN_TITLES = {
    "project": ("١", "بيانات المشروع"),
    "plans": ("٢", "المساقط المعمارية"),
    "building": ("٣", "الأدوار والمناسيب"),
    "ai": ("٤", "مراجعة الذكاء الاصطناعي"),
}


def goto(screen: str) -> None:
    st.session_state.screen = screen
    st.rerun()


def project_ready() -> bool:
    p = st.session_state.project
    return bool(p.get("name", "").strip() and p.get("location", "").strip() and p.get("use", "").strip())


def ground_ready() -> bool:
    return isinstance(st.session_state.plan_candidates.get("ground"), dict)


def building_ready() -> bool:
    return isinstance(st.session_state.building_model, dict)


def ai_ready() -> bool:
    return bool(st.session_state.ai_test_ok and st.session_state.ai_tested_model == st.session_state.ai_selected_model)


def plans_step_ready() -> bool:
    return ground_ready() and bool(st.session_state.plans_reviewed)


def completion_count() -> int:
    return sum([project_ready(), plans_step_ready(), building_ready(), ai_ready()])


def next_home_screen() -> tuple[str, str]:
    """Return the single next action so the home screen does not become a menu maze."""
    if not project_ready():
        return "project", "ابدأ إعداد المشروع"
    if not plans_step_ready():
        return "plans", "الخطوة التالية: ارفع المساقط"
    if not building_ready():
        return "building", "الخطوة التالية: كوّن المبنى"
    if not ai_ready():
        return "ai", "الخطوة التالية: افتح الوكيل الذكي"
    return "building", "افتح مراجعة المبنى"


def render_topbar() -> None:
    brand = "<div style='font-weight:800;font-size:1.15rem;color:#176B87'>🏗️ Structural Studio <span style='font-size:.82rem;color:#68788A;font-weight:500'>| مهندس المبنى</span></div>"
    if st.session_state.screen == "home":
        st.markdown(brand, unsafe_allow_html=True)
    else:
        c_brand, c_home = st.columns([5, 1])
        with c_brand:
            st.markdown(brand, unsafe_allow_html=True)
        with c_home:
            if st.button("الرئيسية", key="nav_home", use_container_width=True):
                goto("home")
    if st.session_state.screen != "home":
        status = {
            "project": project_ready(), "plans": plans_step_ready(),
            "building": building_ready(), "ai": ai_ready(),
        }
        cols = st.columns(4)
        for col, step in zip(cols, ("project", "plans", "building", "ai")):
            no, title = SCREEN_TITLES[step]
            css_class = "active" if st.session_state.screen == step else ("done" if status[step] else "")
            icon = "✓" if status[step] else no
            with col:
                st.markdown(f"<div class='step-chip {css_class}'>{icon}<br>{title}</div>", unsafe_allow_html=True)
        st.progress(completion_count() / 4, text=f"تقدم المشروع: {completion_count()} من 4 خطوات مؤكدة")
    st.markdown("<div class='draft-warning'>مهم: هذا الإصدار يبني مسودة هندسية للمراجعة. التصميم والتسليح النهائيان وفق الكود المصري لم يكتملَا، والمخرجات غير صالحة للتنفيذ.</div>", unsafe_allow_html=True)


def render_footer_nav(previous: str | None, next_screen: str | None, next_label: str = "حفظ ومتابعة ←", *, next_disabled: bool = False) -> None:
    left, spacer, right = st.columns([1.1, 3, 1.5])
    with left:
        if previous and st.button("→ السابق", key=f"prev_{st.session_state.screen}", use_container_width=True):
            goto(previous)
    with right:
        if next_screen and st.button(next_label, key=f"next_{st.session_state.screen}", type="primary", use_container_width=True, disabled=next_disabled):
            goto(next_screen)


def _plan_label(key: str) -> str:
    return {"ground":"الدور الأرضي", "typical":"الدور المتكرر", "basement":"البدروم", "roof":"السطح"}[key]


def _process_uploaded_plans() -> None:
    units = {"مم":0.001, "سم":0.01, "متر":1.0}[st.session_state.plans_units]
    candidates: dict[str, dict[str, Any]] = {}
    analyses: dict[str, dict[str, Any]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    floor_ids = {"ground":"ground", "typical":"typical", "basement":"basement", "roof":"roof"}
    for key, item in st.session_state.plan_uploads.items():
        if not item:
            continue
        raw = item["bytes"]
        name = item["name"]
        summaries[key] = inspect_dxf_bytes(raw, name)
        analyses[key] = analyze_dxf_structure(raw, name)
        candidates[key] = make_architectural_plan_candidate(
            raw, name, metres_per_drawing_unit=units, units_confirmed=True,
            layer_conventions_confirmed=True, floor_identity=floor_ids[key],
            project_fields={"project_name":st.session_state.project.get("name"), "location":st.session_state.project.get("location")},
        )
    st.session_state.plan_candidates = candidates
    st.session_state.plan_analyses = analyses
    st.session_state.plan_summaries = summaries
    st.session_state.plans_reviewed = False
    st.session_state.building_model = None
    st.session_state.building_preview = None
    st.session_state.building_package = None


def _build_stack_from_ui() -> None:
    cfg = st.session_state.building_config_input
    candidates = st.session_state.plan_candidates
    model = build_multistorey_building_candidate(
        cfg,
        ground_plan=candidates.get("ground"), typical_plan=candidates.get("typical"),
        basement_plan=candidates.get("basement"), roof_plan=candidates.get("roof"),
    )
    preview = render_building_stack_preview_png(model)
    sources = {item["name"]: item["bytes"] for item in st.session_state.plan_uploads.values() if item}
    package = create_building_stack_review_package(model, preview, sources)
    st.session_state.building_model = model
    st.session_state.building_preview = preview
    st.session_state.building_package = package


# -------------------- Header --------------------
render_topbar()

screen = st.session_state.screen

# -------------------- Home --------------------
if screen == "home":
    st.markdown("<div class='hero'><h1>خلّينا نبني النموذج مع بعض</h1><p>ارفع الرسم المعماري، وضّح عدد الأدوار وارتفاعاتها، وبعدها خلّي الوكيل يراجع البيانات ويقترح الخطوة التالية. مش مطلوب منك ترسم النموذج الإنشائي بنفسك.</p></div>", unsafe_allow_html=True)
    p = st.session_state.project
    st.markdown("### مشروعك الحالي")
    a,b,c = st.columns([2,1,1])
    with a:
        st.markdown(f"<div class='step-card'><div class='small-muted'>اسم المشروع</div><div style='font-size:1.35rem;font-weight:800;color:#172B4D'>{p.get('name') or 'لم يتم تسمية المشروع بعد'}</div><div class='small-muted'>{p.get('location') or 'أدخل المدينة في الخطوة الأولى'}</div></div>", unsafe_allow_html=True)
    with b:
        st.markdown(f"<div class='step-card'><div class='small-muted'>المسقط الأرضي</div><div style='font-size:1.25rem;font-weight:800;color:#176B87'>{'جاهز للمراجعة' if ground_ready() else 'لم يُرفع بعد'}</div></div>", unsafe_allow_html=True)
    with c:
        st.markdown(f"<div class='step-card'><div class='small-muted'>حالة الذكاء الاصطناعي</div><div style='font-size:1.15rem;font-weight:800;color:{'#16794B' if ai_ready() else '#9A6700'}'>{'تم اختبار الرد' if ai_ready() else 'لم يُختبر بعد'}</div></div>", unsafe_allow_html=True)
    st.markdown("### رحلتك في البرنامج")
    cards = [
        ("١", "بيانات المشروع", "اسم المبنى والمدينة والاستخدام.", project_ready()),
        ("٢", "المساقط المعمارية", "الأرضي والمتكرر، ثم مراجعة قراءة الرسم.", plans_step_ready()),
        ("٣", "الأدوار والمناسيب", "عدد الأدوار والارتفاعات والبدروم والسطح.", building_ready()),
        ("٤", "مراجعة الوكيل", "الوكيل يفحص البيانات ويشرح النواقص بعد اختبار AI.", ai_ready()),
    ]
    cols = st.columns(4)
    for col, (num,title,desc,done) in zip(cols,cards):
        with col:
            badge = "✓ مكتمل" if done else "التالي عند الحاجة"
            st.markdown(f"<div class='step-card'><div class='step-no'>{'✓' if done else num}</div><div style='font-weight:800;color:#172B4D;font-size:1.02rem'>{title}</div><div class='small-muted' style='margin-top:6px'>{desc}</div><div style='margin-top:12px;color:{'#176B45' if done else '#68788A'};font-size:.82rem;font-weight:700'>{badge}</div></div>", unsafe_allow_html=True)
    target, action_label = next_home_screen()
    st.markdown("<div class='cta-panel'><h3>الخطوة التالية فقط</h3><div class='small-muted'>مش محتاج تختار من قوائم كتير. اضغط الزر، والبرنامج هيمشي معاك خطوة خطوة.</div></div>", unsafe_allow_html=True)
    if st.button(action_label, key="home_continue", type="primary", use_container_width=True):
        goto(target)
    st.markdown("### آخر ما تم إنجازه")
    if building_ready():
        m = st.session_state.building_model
        counts = m.get("counts", {})
        x,y,z = st.columns(3)
        x.metric("المستويات", counts.get("plan_levels_including_basement_and_roof", 0))
        y.metric("مقاطع الأعمدة المرشحة", counts.get("column_segments", 0))
        z.metric("حالة النموذج", "مسودة للمراجعة")
        st.caption("لم يتم تشغيل تحليل أو تصميم تلقائي نتيجة إنشاء النموذج. استخدم زر الخطوة التالية للعودة إلى المراجعة.")
    else:
        st.info("لسه ما أنشأناش نموذج المبنى. ابدأ من بيانات المشروع ثم ارفع البلان.")

# -------------------- Step 1: Project --------------------
elif screen == "project":
    st.markdown("<div class='section-title'>١. عرفني على المبنى</div><div class='section-subtitle'>أدخل المعروف عندك فقط. أي معلومة غير معروفة نقدر نعلّمها كبيانات ناقصة بدل ما نخمنها.</div>", unsafe_allow_html=True)
    p = st.session_state.project
    with st.form("project_details_form"):
        c1,c2 = st.columns(2)
        with c1:
            name = st.text_input("اسم المشروع *", value=p.get("name",""), placeholder="مثال: عمارة سكنية — شارع ...")
            location = st.text_input("المدينة / الموقع *", value=p.get("location",""), placeholder="مثال: الأقصر، مصر")
            use = st.selectbox("استخدام المبنى", ["سكني","إداري","تجاري","تعليمي","صحي","صناعي","متعدد الاستخدامات","أخرى"], index=["سكني","إداري","تجاري","تعليمي","صحي","صناعي","متعدد الاستخدامات","أخرى"].index(p.get("use","سكني")))
            code = st.text_input("مرجع الكود إن كنت تعرفه", value=p.get("code",""), placeholder="اتركه فارغًا لو محتاجين نراجعه")
        with c2:
            fc = st.number_input("مقاومة الخرسانة المحددة (MPa)", min_value=0.0, max_value=120.0, value=float(p.get("fc",30)), step=5.0)
            fy = st.number_input("إجهاد خضوع الحديد المحدد (MPa)", min_value=0.0, max_value=800.0, value=float(p.get("fy",420)), step=25.0)
            soil_status = st.selectbox("تقرير التربة", ["غير متوفر","متوفر","قيد الإعداد"], index=["غير متوفر","متوفر","قيد الإعداد"].index(p.get("soil_status","غير متوفر")))
            soil_notes = st.text_area("ملحوظة عن التربة (اختياري)", value=p.get("soil_notes",""), placeholder="مثال: منسوب المياه أو توصية الأساسات إن وجدت", height=90)
        with st.expander("معلومات إضافية — تقدر تكملها بعدين"):
            live = st.text_area("مصدر الأحمال الحية", value=p.get("live_load_basis",""), placeholder="لو عندك جدول أحمال، اذكره هنا", height=65)
            wind = st.text_area("معلومات الرياح / الزلازل", value=p.get("wind_basis",""), placeholder="اتركه فارغًا لو لم يتم تحديده", height=65)
            seismic = st.text_area("أساس الأحمال الزلزالية", value=p.get("seismic_basis",""), height=65)
            groundwater = st.text_input("منسوب المياه الجوفية إن كان معروفًا", value=p.get("groundwater",""))
        save = st.form_submit_button("حفظ بيانات المشروع ←", type="primary", use_container_width=True)
    if save:
        if not name.strip() or not location.strip():
            st.error("اكتب اسم المشروع والمدينة على الأقل، وبعدها احفظ البيانات.")
        else:
            st.session_state.project = {"name":name.strip(),"location":location.strip(),"use":use,"code":code.strip(),"fc":fc,"fy":fy,"soil_status":soil_status,"soil_notes":soil_notes.strip(),"live_load_basis":live.strip(),"wind_basis":wind.strip(),"seismic_basis":seismic.strip(),"groundwater":groundwater.strip()}
            st.success("اتحفظت بيانات المشروع. هنستخدمها في مراجعة الوكيل وتكوين النموذج.")
            st.rerun()
    st.markdown("#### المطلوب منك الآن")
    st.write("مش لازم تملأ كل شيء. اسم المشروع والموقع هما المطلوبان للمتابعة، والباقي يظهر لاحقًا كبيانات مؤكدة أو ناقصة.")
    render_footer_nav("home", "plans", "التالي: رفع المساقط ←", next_disabled=not project_ready())

# -------------------- Step 2: DXF plans --------------------
elif screen == "plans":
    st.markdown("<div class='section-title'>٢. ارفع الرسومات المعمارية</div><div class='section-subtitle'>ابدأ بملفين فقط: الأرضي والمتكرر. ارفع البدروم أو السطح إذا كان تخطيطهما مختلفًا.</div>", unsafe_allow_html=True)
    if not project_ready():
        st.warning("خلّينا نحفظ اسم المشروع والمدينة أولًا.")
        if st.button("الذهاب إلى بيانات المشروع", type="primary"):
            goto("project")
    st.markdown("#### ملفات DXF")
    upload_specs = [("ground","مسقط الدور الأرضي *","upload_ground"),("typical","مسقط الدور المتكرر","upload_typical")]
    cols = st.columns(2)
    for col,(key,label,widget_key) in zip(cols,upload_specs):
        with col:
            uploaded = st.file_uploader(label, type=["dxf"], key=widget_key, help="ملف DXF منفصل لهذا الدور.")
            if uploaded is not None:
                st.session_state.plan_uploads[key] = {"name":uploaded.name,"bytes":uploaded.getvalue()}
            current = st.session_state.plan_uploads.get(key)
            if current:
                st.success(f"مرفوع: {current['name']} ({len(current['bytes']):,} بايت)")
                if st.button("إزالة الملف", key=f"remove_{key}"):
                    st.session_state.plan_uploads[key] = None
                    st.session_state.plan_candidates.pop(key, None)
                    st.session_state.plan_analyses.pop(key, None)
                    st.session_state.plan_summaries.pop(key, None)
                    st.rerun()
    with st.expander("مساقط إضافية (اختيارية)"):
        x,y = st.columns(2)
        with x:
            basement_up = st.file_uploader("مسقط البدروم", type=["dxf"], key="upload_basement")
            if basement_up is not None:
                st.session_state.plan_uploads["basement"] = {"name":basement_up.name,"bytes":basement_up.getvalue()}
            if st.session_state.plan_uploads.get("basement"):
                st.caption("البدروم: " + st.session_state.plan_uploads["basement"]["name"])
        with y:
            roof_up = st.file_uploader("مسقط السطح", type=["dxf"], key="upload_roof")
            if roof_up is not None:
                st.session_state.plan_uploads["roof"] = {"name":roof_up.name,"bytes":roof_up.getvalue()}
            if st.session_state.plan_uploads.get("roof"):
                st.caption("السطح: " + st.session_state.plan_uploads["roof"]["name"])
    st.markdown("#### تأكيدات بسيطة قبل القراءة")
    c1,c2 = st.columns(2)
    with c1:
        units = st.radio("وحدة الإحداثيات في الرسم", ["مم","سم","متر"], horizontal=True, index=["مم","سم","متر"].index(st.session_state.plans_units), key="plans_units_widget")
        st.session_state.plans_units = units
        units_confirmed = st.checkbox("تأكدت من الوحدة بمقارنة بُعد معروف من الرسم", value=st.session_state.plans_units_confirmed, key="plans_units_confirmed_widget")
        st.session_state.plans_units_confirmed = units_confirmed
    with c2:
        layer_confirmed = st.checkbox("الرسم متبع معيار الطبقات المتفق عليه", value=st.session_state.plans_layers_confirmed, key="plans_layer_confirmed_widget")
        st.session_state.plans_layers_confirmed = layer_confirmed
        st.caption("أمثلة: TEXT لاسم اللوحة، wall 25 cm، column 60x30، beam 30x60، slab.")
    if st.button("اقرأ الرسومات واعرض ما فهمه البرنامج", type="primary", use_container_width=True, disabled=(not st.session_state.plan_uploads.get("ground") or not units_confirmed or not layer_confirmed)):
        try:
            with st.spinner("بنقرأ ملفات DXF ونستخرج الطبقات والعناصر المرشحة..."):
                _process_uploaded_plans()
            st.success("تمت قراءة المساقط. راجع الأعداد والطبقات والتنبيهات بالأسفل.")
        except Exception as exc:
            st.error(f"تعذر قراءة المساقط: {exc}")
    if st.session_state.plan_candidates:
        st.markdown("### ملخص القراءة")
        for key in ("ground","typical","basement","roof"):
            candidate = st.session_state.plan_candidates.get(key)
            if not candidate:
                continue
            with st.expander(f"{_plan_label(key)} — {candidate.get('source_dxf',{}).get('filename', st.session_state.plan_uploads[key]['name'])}", expanded=(key=="ground")):
                counts = candidate.get("component_counts", {})
                m1,m2,m3,m4 = st.columns(4)
                m1.metric("أعمدة مرشحة", counts.get("column",0))
                m2.metric("كمرات مرشحة", counts.get("beam",0))
                m3.metric("حوائط مرشحة", counts.get("wall",0))
                m4.metric("حدود بلاطات", counts.get("slab_outline",0))
                if candidate.get("source_preview_png"):
                    st.image(candidate["source_preview_png"], caption="معاينة تقريبية للرسم — راجع CAD الأصلي عند الشك", use_container_width=True)
                unknown = candidate.get("layer_contract", {}).get("unmapped_layers", [])
                if unknown:
                    st.warning("طبقات لم تُربط تلقائيًا: " + "، ".join(unknown[:20]))
                for warning in candidate.get("plan_warnings", []):
                    st.warning(warning)
                summary = st.session_state.plan_summaries.get(key,{})
                st.caption(f"عدد كيانات CAD: {summary.get('modelspace_entity_count', summary.get('entity_count_modelspace','غير متاح'))} | اسم اللوحة يحتاج تأكيد المهندس.")
        st.checkbox("راجعت الملخص والتصنيفات الظاهرة وأؤكد أنها مسودة تحتاج مراجعة هندسية", key="plans_reviewed")
        if st.session_state.plans_reviewed:
            st.success("تم تأكيد مراجعة القراءة. اضغط زر التالي للانتقال إلى الأدوار والمناسيب.")
        else:
            st.info("راجع الصورة وأعداد العناصر والتنبيهات، ثم ضع علامة التأكيد لتفعيل الخطوة التالية.")
    render_footer_nav("project", "building", "التالي: تكوين المبنى ←", next_disabled=not plans_step_ready())

# -------------------- Step 3: Building levels --------------------
elif screen == "building":
    st.markdown("<div class='section-title'>٣. كوّن المبنى ثلاثي الأبعاد</div><div class='section-subtitle'>بدل رفع لوحة لكل دور، نستخدم الأرضي والمتكرر ونبني المناسيب تلقائيًا من الأرقام التي تدخلها.</div>", unsafe_allow_html=True)
    candidates = st.session_state.plan_candidates
    if not candidates.get("ground"):
        st.warning("ارفع واقرأ مسقط الأرضي أولًا.")
        if st.button("الرجوع للمساقط", type="primary"):
            goto("plans")
    p = st.session_state.project
    a,b,c = st.columns(3)
    with a:
        story_count = st.number_input("عدد الأدوار فوق الأرض (شامل الأرضي)", min_value=1, max_value=100, value=int(st.session_state.get("b_story_count",4)), key="b_story_count")
        ground_h = st.number_input("ارتفاع الأرضي (متر)", min_value=2.0, max_value=12.0, value=float(st.session_state.get("b_ground_h",4.0)), step=0.1, key="b_ground_h")
    with b:
        upper_mode_label = st.radio("ارتفاعات الأدوار العليا", ["نفس الارتفاع","مختلفة لكل دور"], horizontal=False, key="b_upper_mode_label")
        typical_h = st.number_input("ارتفاع المتكرر (متر)", min_value=2.0, max_value=8.0, value=float(st.session_state.get("b_typical_h",3.2)), step=0.1, key="b_typical_h", disabled=(upper_mode_label=="مختلفة لكل دور"))
    with c:
        street_z = st.number_input("منسوب مرجع الشارع (م)", value=float(st.session_state.get("b_street_z",0.0)), step=0.05, key="b_street_z")
        ground_offset = st.number_input("تشطيب الأرضي أعلى/أقل من الشارع (م)", value=float(st.session_state.get("b_ground_offset",0.45)), step=0.05, key="b_ground_offset")
    upper_heights = []
    if story_count > 1 and upper_mode_label == "مختلفة لكل دور":
        st.markdown("**أدخل ارتفاع كل دور حتى السطح**")
        cols = st.columns(min(4, story_count-1))
        for i in range(1,story_count):
            with cols[(i-1) % len(cols)]:
                v = st.number_input(f"ارتفاع الدور {i} إلى {i+1} (م)", min_value=2.0, max_value=8.0, value=float(st.session_state.get(f"b_upper_{i}",3.2)), step=0.1, key=f"b_upper_{i}")
                upper_heights.append(v)
    if story_count > 1:
        if candidates.get("typical"):
            typical_mode = st.radio("مسقط الأدوار المتكررة", ["استخدم المسقط المتكرر المرفوع","الأرضي مطابق للمتكرر (مراجعة مطلوبة)"], key="b_typical_plan_mode")
            typical_plan_mode = "separate" if typical_mode == "استخدم المسقط المتكرر المرفوع" else "same_as_ground"
        else:
            typical_plan_mode = "same_as_ground"
            st.warning("لم ترفع مسقط المتكرر. لاختيار التكرار استخدم تأكيدًا صريحًا — لا نفترض أن الأدوار متطابقة تلقائيًا.")
            st.checkbox("أؤكد استخدام مسقط الأرضي للمتكرر كمرجع مؤقت فقط", key="b_confirm_typical_proxy")
    else:
        typical_plan_mode = "same_as_ground"
    st.markdown("#### البدروم والسطح")
    cc1,cc2 = st.columns(2)
    with cc1:
        basement_enabled = st.checkbox("يوجد بدروم", key="b_basement_enabled")
        basement_count = 0
        basement_h = 3.2
        basement_mode = "uniform"
        if basement_enabled:
            basement_count = st.number_input("عدد أدوار البدروم", min_value=1, max_value=5, value=int(st.session_state.get("b_basement_count",1)), key="b_basement_count")
            basement_h = st.number_input("ارتفاع كل بدروم (متر)", min_value=2.0, max_value=8.0, value=float(st.session_state.get("b_basement_h",3.2)), step=0.1, key="b_basement_h")
            if candidates.get("basement"):
                basement_plan_mode = "separate"
                st.caption("تم رفع مسقط بدروم مستقل.")
            else:
                basement_plan_mode = "ground_footprint_proxy"
                st.warning("لا يوجد مسقط بدروم مستقل. يلزم تأكيد استخدام بصمة الأرضي كمرجع هندسي مؤقت، مع أنها لا تمثل حوائط السند والتربة والمياه.")
                st.checkbox("أفهم حدود المرجع المؤقت وأوافق على استخدامه للمسودة فقط", key="b_confirm_basement_proxy")
        else:
            basement_plan_mode = "separate"
    with cc2:
        if candidates.get("roof"):
            roof_plan_mode = "separate"
            st.success("يوجد مسقط سطح مستقل.")
        else:
            roof_plan_mode = "typical_proxy"
            st.warning("لم ترفع مسقط سطح مستقل؛ غرف السطح والخزانات والفتحات لن تكون ممثلة.")
            st.checkbox("أوافق على استخدام المتكرر مرجعًا مؤقتًا للسطح", key="b_confirm_roof_proxy")
    with st.expander("معلومات التربة والأحمال الجانبية (متقدمة — يمكن استكمالها لاحقًا)"):
        f1,f2 = st.columns(2)
        with f1:
            foundation_label = st.selectbox("مرشح الأساسات فقط (ليس اختيارًا نهائيًا)", ["غير محدد","قواعد منفصلة","قواعد مشتركة","قواعد شريطية","لبشة","خوازيق"], key="b_foundation_label")
            groundwater = st.text_input("منسوب المياه الجوفية بالنسبة للشارع (م)", value=p.get("groundwater",""), key="b_groundwater")
            geotech = st.text_area("ملخص توصيات تقرير التربة", value=p.get("soil_notes",""), key="b_geotech")
        with f2:
            live_basis = st.text_area("مصدر الحمل الحي", value=p.get("live_load_basis",""), key="b_live_basis")
            wind_basis = st.text_area("أساس الرياح", value=p.get("wind_basis",""), key="b_wind_basis")
            seismic_basis = st.text_area("أساس الزلازل", value=p.get("seismic_basis",""), key="b_seismic_basis")
    if st.button("أنشئ نموذج المبنى للمراجعة", type="primary", use_container_width=True, disabled=(not candidates.get("ground") or not st.session_state.get("plans_units_confirmed") or not st.session_state.get("plans_layers_confirmed") or not st.session_state.get("plans_reviewed"))):
        try:
            if story_count > 1 and not candidates.get("typical") and not st.session_state.get("b_confirm_typical_proxy"):
                raise ValueError("أكد استخدام الأرضي كمرجع مؤقت للمتكرر أو ارفع مسقط المتكرر.")
            if basement_enabled and not candidates.get("basement") and not st.session_state.get("b_confirm_basement_proxy"):
                raise ValueError("أكد مرجع البدروم المؤقت أو ارفع مسقط البدروم.")
            if not candidates.get("roof") and not st.session_state.get("b_confirm_roof_proxy"):
                raise ValueError("أكد استخدام المتكرر كمرجع مؤقت للسطح أو ارفع مسقط السطح.")
            foundation_ids = {"غير محدد":"not_selected","قواعد منفصلة":"isolated_footings_candidate","قواعد مشتركة":"combined_footings_candidate","قواعد شريطية":"strip_footings_candidate","لبشة":"raft_candidate","خوازيق":"piles_candidate"}
            cfg = {
                "project_name":p.get("name") or "مشروع جديد", "location":p.get("location") or "غير محدد", "building_use":p.get("use") or "سكني",
                "code_reference":p.get("code") or "غير محدد — يحتاج تأكيد المهندس", "concrete_strength_mpa":p.get("fc"), "steel_yield_strength_mpa":p.get("fy"),
                "above_ground_story_count":int(story_count), "ground_story_height_m":float(ground_h),
                "upper_story_height_mode":"uniform" if upper_mode_label=="نفس الارتفاع" else "individual",
                "upper_story_heights_m":([float(x) for x in upper_heights] if upper_mode_label=="مختلفة لكل دور" else [float(typical_h)]*(int(story_count)-1)),
                "typical_story_height_m":float(typical_h), "ground_finished_floor_offset_from_street_m":float(ground_offset),
                "street_datum_elevation_m":float(street_z), "ground_plan_units_confirmed":True,"layer_conventions_confirmed":True,
                "typical_plan_mode":typical_plan_mode, "basement_enabled":bool(basement_enabled), "basement_count":int(basement_count),
                "basement_height_mode":basement_mode, "basement_story_height_m":float(basement_h), "basement_story_heights_m":[float(basement_h)]*int(basement_count),
                "basement_plan_mode":basement_plan_mode, "roof_plan_mode":roof_plan_mode, "foundation_system_candidate":foundation_ids[foundation_label],
                "foundation_depth_below_lowest_floor_m":None,"soil_report_status":"available" if p.get("soil_status")=="متوفر" else "not_available",
                "geotechnical_notes":geotech, "groundwater_level_m_relative_to_street":None if not groundwater.strip() else float(groundwater),
                "occupancy_load_basis":live_basis,"wind_basis":wind_basis,"seismic_basis":seismic_basis,"site_class":"unknown",
                "plan_irregularities":"not assessed","vertical_irregularities":"not assessed","diaphragm_assumption":"not confirmed",
            }
            st.session_state.building_config_input = cfg
            with st.spinner("بنكوّن المساقط على المناسيب ونفحص الاستمرارية الهندسية..."):
                _build_stack_from_ui()
            st.success("تم تكوين النموذج المرشح. راجع الصورة والتحذيرات قبل المتابعة.")
        except Exception as exc:
            st.error(str(exc))
    if building_ready():
        m = st.session_state.building_model
        st.markdown("### النموذج الذي سنراجعه معك")
        x,y,z = st.columns(3)
        x.metric("المستويات", m.get("counts",{}).get("plan_levels_including_basement_and_roof",0))
        y.metric("مقاطع الأعمدة المرشحة", m.get("counts",{}).get("column_segments",0))
        z.metric("موانع مهمة", len(m.get("critical_missing_inputs",[])))
        if st.session_state.building_preview:
            st.image(st.session_state.building_preview, caption="عرض هندسي تخطيطي للمبنى — ليس نموذج تصميم معتمدًا", use_container_width=True)
        if m.get("critical_missing_inputs"):
            st.warning("بيانات ناقصة قبل التحليل:\n\n" + "\n".join(f"- {x}" for x in m["critical_missing_inputs"][:15]))
        if m.get("warnings"):
            with st.expander("اعرض التنبيهات", expanded=False):
                for warning in m["warnings"][:30]: st.write("• " + str(warning))
        if st.session_state.building_package:
            st.download_button("تحميل حزمة النموذج للمراجعة ZIP", data=st.session_state.building_package, file_name="building_model_review.zip", mime="application/zip", type="primary", use_container_width=True)
        st.caption("إنشاء النموذج لا يشغّل التحليل أو التصميم أو التسليح تلقائيًا.")
    render_footer_nav("plans", "ai", "التالي: تحدث مع الوكيل ←", next_disabled=not building_ready())

# -------------------- Step 4: AI --------------------
elif screen == "ai":
    st.markdown("<div class='section-title'>٤. اتكلم مع الوكيل</div><div class='section-subtitle'>اسأله بالعربي. يستطيع مراجعة ما أدخلته، وقراءة ملخص DXF، وفحص نموذج الأدوار، وتوضيح النواقص. لن يخمّن بيانات غير موجودة.</div>", unsafe_allow_html=True)
    # Simple visible setup panel instead of developer-oriented settings throughout the app.
    with st.container(border=True):
        st.markdown("#### اتصال الذكاء الاصطناعي المحلي")
        if not st.session_state.ai_model_check_done:
            st.info("لم نختبر الاتصال حتى الآن.")
        elif st.session_state.ai_connection_error:
            st.error("مش قادرين نوصل لـ Ollama على جهازك.")
            with st.expander("سبب الخطأ وكيف تصلحه"):
                st.code(st.session_state.ai_connection_error)
                st.write("تأكد أن Ollama يعمل، ثم افتح PowerShell ونفّذ: `ollama pull qwen3.5:2b`.")
        elif st.session_state.ai_models:
            st.success(f"وجدنا {len(st.session_state.ai_models)} نموذجًا محليًا.")
        else:
            st.warning("الخدمة موجودة، لكن لا توجد نماذج محلية محمّلة.")
        c1,c2 = st.columns([1,2])
        with c1:
            if st.button("فحص الاتصال", key="simple_ai_check", type="secondary", use_container_width=True):
                try:
                    st.session_state.ai_models = OllamaClient().list_models()
                    st.session_state.ai_connection_error = None
                    st.session_state.ai_model_check_done = True
                    st.session_state.ai_test_ok = False
                    st.session_state.ai_tested_model = ""
                except Exception as exc:
                    st.session_state.ai_models = []
                    st.session_state.ai_connection_error = str(exc)
                    st.session_state.ai_model_check_done = True
                st.rerun()
        with c2:
            if st.session_state.ai_models:
                names = [str(x.get("name")) for x in st.session_state.ai_models if x.get("name")]
                default = names.index(st.session_state.ai_selected_model) if st.session_state.ai_selected_model in names else 0
                st.selectbox("النموذج المحلي", names, index=default, key="ai_model_pick")
                st.session_state.ai_selected_model = st.session_state.get("ai_model_pick", names[default])
                if st.button("اختبر أن النموذج يرد فعلًا", key="simple_ai_test", type="primary", use_container_width=True):
                    try:
                        with st.spinner("أول رد قد يحتاج بعض الوقت على جهاز 8 جيجا RAM..."):
                            ans = OllamaClient().chat(st.session_state.ai_selected_model,[
                                {"role":"system","content":"أجب بالعربية بكلمة واحدة: جاهز."},
                                {"role":"user","content":"اختبار اتصال بسيط."},
                            ],temperature=0.0,num_ctx=1024,num_predict=24)
                        st.session_state.ai_test_ok = True
                        st.session_state.ai_tested_model = st.session_state.ai_selected_model
                        st.session_state.ai_test_result = ans
                        st.session_state.ai_test_error = ""
                    except Exception as exc:
                        st.session_state.ai_test_ok = False
                        st.session_state.ai_tested_model = st.session_state.ai_selected_model
                        st.session_state.ai_test_error = str(exc)
                    st.rerun()
                if ai_ready():
                    st.success("الوكيل جاهز — النموذج رد فعلًا: " + st.session_state.ai_test_result[:250])
                elif st.session_state.ai_test_error:
                    st.error("النموذج لم ينجح في الرد: " + st.session_state.ai_test_error)
                else:
                    st.caption("لا يمكن بدء المحادثة قبل نجاح اختبار الرد الحي.")
            else:
                st.write("للتشغيل لأول مرة: ثبّت Ollama، ثم حمّل `qwen3.5:2b` بالأمر `ollama pull qwen3.5:2b`.")
    if not ai_ready():
        st.warning("المحادثة متوقفة حتى ينجح اختبار الرد الحقيقي. ده يمنع الواجهة من إظهار أنها تتحدث مع AI وهي غير متصلة.")
    else:
        # Render chat history in the common familiar format.
        for msg in st.session_state.chat_history[-12:]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        prompt = st.chat_input("مثال: راجع المسقط وقل لي أهم 3 نواقص قبل تكوين النموذج...")
        if prompt:
            st.session_state.chat_history.append({"role":"user","content":prompt})
            project = st.session_state.project
            ground = st.session_state.plan_uploads.get("ground")
            dxf_summary = st.session_state.plan_summaries.get("ground")
            dxf_analysis = st.session_state.plan_analyses.get("ground")
            current_building_config = st.session_state.get("building_config_input") or {}
            state = {
                "project_fields": {
                    "project_name":project.get("name"),"project_number":project.get("number"),"location":project.get("location"),
                    "building_use":project.get("use"),"stories_above_ground":current_building_config.get("above_ground_story_count"),
                    "story_height_m":current_building_config.get("ground_story_height_m"),
                    "specified_concrete_strength_MPa":project.get("fc"),"specified_steel_yield_strength_MPa":project.get("fy"),
                    "code_reference_as_entered":project.get("code"),"soil_report_status":project.get("soil_status"),"soil_notes":project.get("soil_notes"),
                    "live_load_source_as_entered":project.get("live_load_basis"),"lateral_load_basis_as_entered":(project.get("wind_basis","")+" "+project.get("seismic_basis","" )).strip(),
                },
                "dxf_summary":dxf_summary,"dxf_structural_analysis":dxf_analysis,
                "source_dxf_bytes":ground.get("bytes") if ground else None,"source_dxf_name":ground.get("name") if ground else "drawing.dxf",
                "dxf_review_rows":[],"dxf_review_confirmed":bool(st.session_state.plans_reviewed),
                "dxf_units_confirmed":bool(st.session_state.plans_units_confirmed),"dxf_layer_dimensions_confirmed":bool(st.session_state.plans_layers_confirmed),
                "dxf_candidate_model":None,"building_stack_config":current_building_config or None,
                "building_stack_model":st.session_state.get("building_model"),"building_stack_plan_candidates":st.session_state.plan_candidates,
                "is_demo_project":not project.get("name") or "demo" in str(project.get("name")).lower(),
                "allow_demo_analysis":False,"confirm_current_inputs":False,"regular_grid_confirmed":False,
                "demo_tool_flags":{"frame2d":True,"frame3d":True,"plate_shell":True,"punching":True},
            }
            runtime: dict[str,Any] = {}
            try:
                tools = build_engineering_tools(state,runtime)
                safe_names = {"inspect_project_status","inspect_uploaded_dxf","inspect_multistorey_building_context","preflight_building_model_connectivity","infer_dxf_structural_geometry","list_structural_system_options"}
                tools = [tool for tool in tools if tool.name in safe_names]
                context_lines = ["بيانات المشروع الحالية (قد تكون ناقصة):",json.dumps(state["project_fields"],ensure_ascii=False),
                    "ملخص المبنى:", json.dumps((st.session_state.building_model or {}).get("counts",{}),ensure_ascii=False),
                    "",
                    "طلب المستخدم: " + prompt]
                messages = [{"role":"user","content":"\n".join(context_lines)}]
                image_bytes = None
                if ground and dxf_analysis:
                    try:
                        from structural_engine.dxf_preview import render_dxf_preview_png
                        image_bytes = render_dxf_preview_png(ground["bytes"],ground["name"])
                    except Exception:
                        pass
                with st.spinner("الوكيل يفهم طلبك، وقد يستدعي أدوات فحص ثم يقرأ نتائجها..."):
                    result = EngineeringAgent(max_tool_calls=5,max_model_rounds=6).run(st.session_state.ai_selected_model,messages,tools,image_bytes=image_bytes)
                st.session_state.latest_agent_result = {"final_text":result.final_text,"stopped_reason":result.stopped_reason,"tool_results":result.tool_results}
                st.session_state.agent_traces.append(result.trace)
                st.session_state.chat_history.append({"role":"assistant","content":result.final_text})
            except Exception as exc:
                st.session_state.chat_history.append({"role":"assistant","content":f"تعذر إكمال الطلب: {exc}\n\nتأكد من أن Ollama ما زال يعمل وأن النموذج المختار يدعم استدعاء الأدوات."})
            st.rerun()
        latest = st.session_state.latest_agent_result
        if isinstance(latest,dict) and latest.get("tool_results"):
            with st.expander("تفاصيل ما فعله الوكيل", expanded=False):
                st.caption("هذا سجل تنفيذ، وليس تأكيدًا أن التصميم الهندسي مكتمل.")
                st.json({"stopped_reason":latest.get("stopped_reason"),"tool_names":list(latest.get("tool_results",{}))})
                if st.session_state.agent_traces:
                    st.dataframe([{"الأداة":r.get("tool"),"الحالة":r.get("status"),"المدة (ث)":r.get("duration_seconds")} for batch in st.session_state.agent_traces[-1] for r in batch],use_container_width=True,hide_index=True)
        st.caption("الوكيل يستطيع مراجعة وتفسير النواقص. لا يعتمد التصميم ولا يصدر تسليحًا تنفيذيًا في هذا الإصدار.")
    left, right = st.columns([1,1])
    with left:
        if st.button("مسح المحادثة", key="clear_simple_chat", use_container_width=True):
            st.session_state.chat_history=[]
            st.session_state.latest_agent_result=None
            st.rerun()
    with right:
        if st.button("العودة لرؤية النموذج", key="back_to_building", use_container_width=True):
            goto("building")

# Simple guidance strip appears on every screen.
st.markdown("<hr><div class='small-muted'>Structural Studio محلي • لا توجد رسوم API • النماذج والمخرجات حالياً للمراجعة فقط وغير صالحة للتنفيذ.</div>", unsafe_allow_html=True)
