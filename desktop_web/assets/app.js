'use strict';

const $ = (id) => document.getElementById(id);
const FLOOR_LABELS = {ground:'الدور الأرضي', typical:'الدور المتكرر', basement:'البدروم', roof:'السطح'};
const VIEW_LABELS = {home:'نظرة عامة', project:'بيانات المشروع', plans:'المساقط المعمارية', building:'الأدوار والمناسيب', review:'مراجعة النموذج'};
const state = {
  view:'home', workspace:null, ai:{reachable:false,models:[],tested:false}, chat:[], lastTrace:[],
  loading:false, selectedUnits:'mm', advancedProject:false, advancedBuilding:false, variableHeights:false,
  files:{ground:null,typical:null,basement:null,roof:null},
};

async function api(path, options={}) {
  const response = await fetch(path, options);
  let body;
  try { body = await response.json(); } catch (_) { body = {}; }
  if (!response.ok) throw new Error(body.detail || body.message || `خطأ HTTP ${response.status}`);
  return body;
}
function esc(v='') { return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function fmt(n, digits=0) { return n === undefined || n === null || n === '' || !Number.isFinite(Number(n)) ? '—' : Number(n).toLocaleString('en-US',{maximumFractionDigits:digits,minimumFractionDigits:0}); }
function toast(message, kind='') { const node=document.createElement('div'); node.className=`toast ${kind}`; node.textContent=message; $('toastHost').appendChild(node); setTimeout(()=>node.remove(),4200); }
function setLoading(on,title='جاري التنفيذ...',subtitle='قد يستغرق الأمر قليلًا') { state.loading=on; $('globalLoading').classList.toggle('hidden',!on); $('loadingTitle').textContent=title; $('loadingSubtitle').textContent=subtitle; }
function nextFrame() { return new Promise(resolve=>requestAnimationFrame(resolve)); }
function go(view) { state.view=view; render(); window.scrollTo({top:0,behavior:'smooth'}); }
function projectReady() { const p=state.workspace?.project||{}; return Boolean(p.name && p.location); }
function plansReady() { return Boolean(state.workspace?.plans_reviewed && state.workspace?.plans?.ground); }
function buildingReady() { return Boolean(state.workspace?.building); }
function aiReady() { return Boolean(state.ai.tested && state.ai.tested_model === state.ai.chosen_model); }
function progress() { const items=[projectReady(),plansReady(),buildingReady(),aiReady()]; return {items,done:items.filter(Boolean).length}; }
function activeNext() { if(!projectReady())return ['project','أكمل بيانات المشروع']; if(!plansReady())return ['plans','ارفع المسقط الأرضي وراجعه']; if(!buildingReady())return ['building','حدد الأدوار وكوّن النموذج']; return ['review','راجع النموذج والموانع']; }

function updateChrome() {
  const project=state.workspace?.project||{};
  $('sideProjectName').textContent=project.name||'مشروع جديد';
  $('sideProjectLocation').textContent=project.location||'لم تحفظ بيانات المشروع';
  $('crumbTitle').textContent=VIEW_LABELS[state.view]||'نظرة عامة';
  document.querySelectorAll('.nav-item').forEach(el=>el.classList.toggle('active',el.dataset.view===state.view));
  const p=progress();
  [['navProjectState',p.items[0],'١'],['navPlansState',p.items[1],'٢'],['navBuildingState',p.items[2],'٣'],['navReviewState',p.items[3],'٤']].forEach(([id,done,n])=>{const el=$(id);el.textContent=done?'✓':n;el.classList.toggle('done',done);});
  const connected=$('aiConnectionDot'); connected.classList.toggle('good',aiReady()); connected.classList.toggle('bad',state.ai.reachable&&!aiReady());
}
function pageHead(kicker,title,description,action='') { return `<div class="page-head"><div><div class="eyebrow">${kicker}</div><h1>${title}</h1><p>${description}</p></div>${action?`<div class="page-actions">${action}</div>`:''}</div>`; }
function notice(type,title,body,icon='!') { return `<div class="notice ${type}"><span class="notice-icon">${icon}</span><div><strong>${title}</strong><div>${body}</div></div></div>`; }
function emptyState(icon,title,description,buttonText,view) { return `<div class="empty-state"><div class="empty-icon">${icon}</div><h3>${title}</h3><p>${description}</p>${buttonText?`<button class="btn btn-primary" data-go="${view}">${buttonText} ←</button>`:''}</div>`; }
function renderHome() {
  const p=state.workspace?.project||{}; const b=state.workspace?.building; const pro=progress(); const [nextView,nextLabel]=activeNext();
  const steps=[
    {n:'١',title:'بيانات المشروع',desc:'اسم المبنى، الموقع، والاستخدام.',done:pro.items[0],view:'project'},
    {n:'٢',title:'المساقط المعمارية',desc:'رفع الأرضي والمتكرر ومراجعة ما قرأه البرنامج.',done:pro.items[1],view:'plans'},
    {n:'٣',title:'الأدوار والمناسيب',desc:'عدد الأدوار والارتفاعات والبدروم والسطح.',done:pro.items[2],view:'building'},
    {n:'٤',title:'مراجعة النموذج',desc:'مراجعة الاتصال والنواقص قبل أي تحليل.',done:pro.items[3],view:'review'},
  ];
  const hero=!projectReady()
    ? `<section class="hero-card"><div class="hero-content"><div class="hero-kicker">مساحة عمل هندسية محلية</div><h1>ابدأ بالمبنى. سنرشدك خطوة بخطوة.</h1><p>لا تحتاج إلى معرفة أسماء المحركات أو إعدادات التحليل. أدخل البيانات الأساسية، ارفع المساقط، وراجع ما فهمه البرنامج مع المساعد الذكي.</p><button class="btn btn-primary" data-go="project">ابدأ مشروعك الأول <span>←</span></button><div class="hero-meta"><span><i></i> يعمل على جهازك</span><span><i></i> لا يحتاج API مدفوع</span><span><i></i> المساعد المحلي اختياري</span></div></div></section>`
    : `<section class="hero-card"><div class="hero-content"><div class="hero-kicker">المشروع الحالي</div><h1>${esc(p.name||'مشروعك الإنشائي')}</h1><p>كمّل مرحلة واحدة في كل مرة. سنعرض لك البيانات الناقصة قبل الانتقال للخطوة التالية.</p><button class="btn btn-primary" data-go="${nextView}">${nextLabel} <span>←</span></button><div class="hero-meta"><span><i></i>${esc(p.location||'الموقع غير محدد')}</span><span><i></i>${pro.done} من 4 مراحل مكتملة</span><span><i></i>المخرجات مسودات مراجعة</span></div></div></section>`;
  const nextMeta={
    project:['بيانات المشروع','احفظ الاسم والموقع والاستخدام.','ستحتاج إلى 3 معلومات أساسية فقط للبدء.'],
    plans:['المساقط المعمارية','ارفع مسقط الدور الأرضي وراجع الطبقات والوحدات.','يمكن إضافة المتكرر والبدروم والسطح عند الحاجة.'],
    building:['الأدوار والمناسيب','حدد عدد الأدوار وارتفاعاتها ومنسوب الشارع.','يمكنك استخدام ارتفاع موحد أو إدخال ارتفاع منفصل لكل دور.'],
    review:['مراجعة النموذج','راجع اتصال العناصر والموانع المسجلة.','لا يبدأ التحليل إذا كانت بيانات أساسية غير محسومة.']
  }[nextView];
  return `${hero}
    <div class="overview-grid">
      <section class="card project-summary"><div class="card-head"><div><div class="eyebrow">ملخص المشروع</div><h2 class="card-title">حالة البيانات</h2></div><span class="badge ${projectReady()?'green':'gray'}">${projectReady()?'محفوظة':'لم يبدأ بعد'}</span></div><div class="summary-name">${esc(p.name||'مبنى جديد')}</div><div class="summary-location">${esc(p.location||'اسم المشروع والموقع غير محفوظين')}</div><div class="summary-stats"><div class="summary-stat"><span>المساقط المقروءة</span><strong>${Object.keys(state.workspace?.plans||{}).length} / 4</strong></div><div class="summary-stat"><span>مستويات النموذج</span><strong>${fmt(b?.counts?.plan_levels_including_basement_and_roof)}</strong></div><div class="summary-stat"><span>الموانع الحرجة</span><strong>${fmt(b?.critical_missing_inputs?.length)}</strong></div></div></section>
      <section class="card next-step-card"><div class="next-step-symbol">${nextView==='project'?'١':nextView==='plans'?'٢':nextView==='building'?'٣':'٤'}</div><div class="eyebrow">الخطوة المطلوبة الآن</div><h2>${nextMeta[0]}</h2><p>${nextMeta[1]}</p><div class="next-step-note">${nextMeta[2]}</div></section>
    </div>
    <div class="section-heading"><div><h2>مراحل المشروع</h2><p>اتبع الترتيب؛ كل مرحلة تجهز البيانات اللازمة للمرحلة التالية.</p></div><span class="badge teal">${pro.done} من 4</span></div>
    <div class="progress-caption"><span>التقدم العام</span><span>${Math.round(pro.done/4*100)}%</span></div><div class="progress-track"><span style="width:${pro.done/4*100}%"></span></div>
    <div class="workflow-list" style="margin-top:14px">${steps.map(s=>`<article class="workflow-card ${s.done?'done':s.view===nextView?'active':''}"><div class="workflow-top"><div class="workflow-number">${s.done?'✓':s.n}</div><span class="workflow-status">${s.done?'مكتملة':s.view===nextView?'الخطوة الحالية':'تأتي لاحقًا'}</span></div><h3>${s.title}</h3><p>${s.desc}</p></article>`).join('')}</div>
    <div class="notice warn" style="margin-top:17px"><span class="notice-icon">ⓘ</span><div><strong>حدود النسخة الحالية</strong><div>البرنامج يساعد في قراءة الرسم وتكوين نموذج مرشح. التحليل والتصميم والتسليح المطابق للكود المصري لم تكتمل بعد؛ المخرجات غير صالحة للتنفيذ.</div></div></div>`;
}
function renderProject() {
  const p=state.workspace?.project||{};
  return `${pageHead('المرحلة ١ من ٤','عرّف المشروع','أدخل البيانات المعروفة فقط. أي شيء ناقص سيظهر لاحقًا كسؤال واضح بدل أن يخمّنه البرنامج.','<span class="badge teal">١ / ٤</span>')}
    <form id="projectForm" class="card card-pad"><div class="card-head"><div><h2 class="card-title">بيانات المبنى الأساسية</h2><div class="card-subtitle">الاسم والموقع والاستخدام تكفي للحفظ والانتقال للخطوة التالية.</div></div><span class="badge gray">الحقول بعلامة * مطلوبة</span></div>
      <div class="form-grid"><div class="field"><label>اسم المشروع <span class="required">*</span></label><input class="control" name="name" required maxlength="160" value="${esc(p.name||'')}" placeholder="مثال: عمارة سكنية — شارع رئيسي"></div><div class="field"><label>المدينة / الموقع <span class="required">*</span></label><input class="control" name="location" required maxlength="160" value="${esc(p.location||'')}" placeholder="مثال: الأقصر، مصر"></div><div class="field"><label>استخدام المبنى</label><select class="control" name="use">${['سكني','إداري','تجاري','تعليمي','صحي','صناعي','متعدد الاستخدامات','أخرى'].map(x=>`<option ${p.use===x?'selected':''}>${x}</option>`).join('')}</select><div class="field-help">لو الاستخدام مختلف من دور لآخر، اذكره للمساعد بعد حفظ المشروع.</div></div><div class="field"><label>مرجع الكود</label><input class="control" name="code" value="${esc(p.code||'ECP 203-2025 — يحتاج التحقق من النص المعتمد')}" placeholder="مرجع الكود وإصداره"></div></div>
      <div class="divider"></div><div class="section-heading" style="margin-top:0"><div><h2>خواص المواد المتوقعة</h2><p>مدخلات أولية من المهندس؛ لا تعتبر تأكيدًا لمواصفات التصميم.</p></div></div>
      <div class="form-grid"><div class="field"><label>مقاومة الخرسانة المحددة (MPa)</label><input class="control" type="number" name="fc" min="1" max="120" step="1" value="${Number(p.fc||30)}"></div><div class="field"><label>إجهاد خضوع الحديد (MPa)</label><input class="control" type="number" name="fy" min="1" max="800" step="10" value="${Number(p.fy||420)}"></div></div>
      <details class="advanced-details" style="margin-top:18px"><summary class="advanced-toggle">بيانات إضافية (تقدر تكملها بعدين) <span>＋</span></summary><div class="form-grid" style="margin-top:12px"><div class="field"><label>حالة تقرير التربة</label><select class="control" name="soil_status">${['غير متوفر','متوفر','قيد الإعداد'].map(x=>`<option ${p.soil_status===x?'selected':''}>${x}</option>`).join('')}</select></div><div class="field"><label>منسوب المياه الجوفية بالنسبة للشارع (م)</label><input class="control" name="groundwater" value="${esc(p.groundwater||'')}" placeholder="اتركه فارغًا لو غير معروف"></div><div class="field"><label>ملخص تقرير التربة</label><textarea class="control" name="soil_notes" rows="3" placeholder="توصيات الأساسات، قدرة التحمل، الهبوط...">${esc(p.soil_notes||'')}</textarea></div><div class="field"><label>مصدر الأحمال الحية</label><textarea class="control" name="live_load_basis" rows="3" placeholder="جدول الأحمال أو مرجعها">${esc(p.live_load_basis||'')}</textarea></div><div class="field"><label>أساس الرياح</label><textarea class="control" name="wind_basis" rows="2">${esc(p.wind_basis||'')}</textarea></div><div class="field"><label>أساس الزلازل</label><textarea class="control" name="seismic_basis" rows="2">${esc(p.seismic_basis||'')}</textarea></div></div></details>
      <div class="step-footer"><span class="hint">تقدر ترجع وتعدّل البيانات لاحقًا.</span><div class="right-actions"><button class="btn btn-outline" type="button" data-go="home">إلغاء</button><button class="btn btn-primary" type="submit">حفظ ومتابعة إلى المساقط ←</button></div></div></form>`;
}
function planCard(floor, title, subtitle, required=false) {
  const plan=state.workspace?.plans?.[floor];
  const current = plan ? `<div class="plan-result"><div class="plan-result-head"><strong title="${esc(plan.filename)}">${esc(plan.filename)}</strong><span class="badge ${plan.warnings?.length?'amber':'green'}">${plan.warnings?.length?'يحتاج مراجعة':'تمت القراءة'}</span></div><div class="plan-result-body">${plan.preview_data_url?`<img class="plan-preview" alt="معاينة ${esc(title)}" src="${plan.preview_data_url}">`:''}<div class="stat-row"><div class="mini-stat"><strong>${fmt(plan.entity_count)}</strong><span>عنصر CAD</span></div><div class="mini-stat"><strong>${fmt(plan.layer_count)}</strong><span>Layer</span></div><div class="mini-stat"><strong>${fmt(Object.values(plan.component_counts||{}).reduce((a,b)=>a+Number(b||0),0))}</strong><span>عنصر مرشح</span></div></div><div class="layer-list">${(plan.layers||[]).slice(0,14).map(l=>`<span class="layer-chip">${esc(l.name)} · ${fmt(l.entity_count)}</span>`).join('')}${(plan.layers||[]).length>14?`<span class="layer-chip">+${plan.layers.length-14} طبقات</span>`:''}</div>${(plan.warnings||[]).map(w=>`<div class="warning-item" style="margin-top:7px">${esc(w)}</div>`).join('')}<div style="display:flex;justify-content:space-between;gap:8px;margin-top:10px"><span class="field-help">الوحدة: ${({mm:'مم',cm:'سم',m:'متر'})[plan.units]||plan.units}</span><button class="btn btn-danger btn-small" data-delete-plan="${floor}">إزالة / استبدال</button></div></div></div>`:
  `<label class="dropzone" for="file-${floor}"><span class="upload-icon">↑</span><strong>اسحب ملف DXF هنا أو اضغط للاختيار</strong><span>الملف يقرأ محليًا على جهازك · حد أقصى 30 MB</span><input id="file-${floor}" type="file" accept=".dxf,application/dxf" data-upload-floor="${floor}"></label>`;
  return `<article class="upload-card"><div class="upload-card-head"><div class="floor-icon">${floor==='ground'?'▤':floor==='typical'?'▥':floor==='basement'?'▦':'⌂'}</div><div><strong>${title}${required?' *':''}</strong><span>${subtitle}</span></div><span class="badge ${plan?'green':'gray'}">${plan?'مرفوع':'اختياري'}</span></div><div class="upload-card-body">${current}</div></article>`;
}
function renderPlans() {
  const p=state.workspace||{};const plans=p.plans||{};
  return `${pageHead('المرحلة ٢ من ٤','ارفع المساقط المعمارية','ارفع مسقط الأرضي ومسقط المتكرر فقط. المساقط الإضافية تستخدم لو البدروم أو السطح مختلفين.','<button class="btn btn-outline" data-go="project">← بيانات المشروع</button>')}
    <div class="card card-pad" style="margin-bottom:14px"><div class="card-head"><div><h2 class="card-title">تأكيد إعدادات الرسم قبل الرفع</h2><div class="card-subtitle">نحتاج وحدة القياس ومعيار الطبقات عشان ما نفسّرش الرسم بشكل غلط.</div></div><span class="badge amber">مراجعة مطلوبة</span></div><div class="form-grid"><div class="field"><label>وحدة الإحداثيات داخل DXF</label><select id="drawingUnits" class="control"><option value="mm" ${state.selectedUnits==='mm'?'selected':''}>ملليمتر (mm)</option><option value="cm" ${state.selectedUnits==='cm'?'selected':''}>سنتيمتر (cm)</option><option value="m" ${state.selectedUnits==='m'?'selected':''}>متر (m)</option></select><div class="field-help">اختر الوحدة الفعلية للرسم، وليس وحدة الأبعاد المكتوبة فقط.</div></div><div class="field"><label>معيار تسمية الطبقات</label><div class="notice info"><span class="notice-icon">ⓘ</span><div>مثال: <b>wall 25 cm</b> و<b>column 60x30</b> و<b>beam 30x60</b> و<b>slab</b>، واسم الدور على Layer باسم <b>TEXT</b>.</div></div></div></div><label class="checkline" style="margin-top:13px"><input id="confirmLayerStandard" type="checkbox" ${p.layer_contract_confirmed?'checked':''}> أؤكد أن وحدة الرسم صحيحة وأن أسماء الطبقات تتبع المعيار الموضح، وسأراجع نتيجة القراءة قبل اعتمادها.</label></div>
    <div class="section-heading"><div><h2>المساقط الأساسية</h2><p>ابدأ بالأرضي. لو المتكرر مطابق تمامًا للأرضي، يمكن تأكيد ذلك في الخطوة التالية.</p></div><span class="badge ${plans.ground?'green':'amber'}">${plans.ground?'الأرضي مرفوع':'الأرضي مطلوب'}</span></div><div class="upload-grid">${planCard('ground','مسقط الدور الأرضي','الرسم المعماري المرجعي',true)}${planCard('typical','مسقط الدور المتكرر','ارفعه لو التخطيط مختلف عن الأرضي',false)}</div>
    <details class="advanced-details" style="margin-top:13px"><summary class="advanced-toggle">مساقط إضافية عند الحاجة <span>＋</span></summary><div class="upload-grid" style="margin-top:10px">${planCard('basement','مسقط البدروم','ارفعه لو موجود أو مختلف عن بصمة الأرضي')}${planCard('roof','مسقط السطح','مهم لو توجد غرف أو خزانات أو فتحات مختلفة')}</div></details>
    ${plans.ground?`<div class="card card-pad" style="margin-top:14px"><div class="card-head"><div><h2 class="card-title">مراجعة قراءة الرسم</h2><div class="card-subtitle">راجع المعاينة وعدد العناصر والطبقات. القراءة ليست اعتمادًا لوظيفة كل خط.</div></div><span class="badge ${p.plans_reviewed?'green':'amber'}">${p.plans_reviewed?'تم تأكيد المراجعة':'بانتظار تأكيدك'}</span></div><label class="checkline"><input id="confirmPlanReview" type="checkbox" ${p.plans_reviewed?'checked':''}> راجعت معاينة المسقط الأرضي وأسماء الطبقات وعدد العناصر، وسأراجع أي اختلافات قبل بناء النموذج.</label><div class="step-footer"><span class="hint">بعد التأكيد، يمكنك تحديد عدد الأدوار والارتفاعات.</span><div class="right-actions"><button class="btn btn-primary" id="confirmPlansBtn" ${p.plans_reviewed?'disabled':''}>تأكيد المساقط والمتابعة ←</button></div></div></div>`:''}`;
}
function renderBuilding() {
  const p=state.workspace||{}; const planCount=Object.keys(p.plans||{}).length; const cfg=p.building?.config||{};
  const typicalMissing=!p.plans?.typical, basementMissing=!p.plans?.basement, roofMissing=!p.plans?.roof;
  return `${pageHead('المرحلة ٣ من ٤','كوّن المبنى من المساقط','حدد عدد الأدوار والارتفاعات والمناسيب. البرنامج يكرر مسقط المتكرر بدل طلب لوحة مستقلة لكل دور.','<button class="btn btn-outline" data-go="plans">← رجوع للمساقط</button>')}
  ${!p.plans_reviewed?notice('warn','المساقط لم تُؤكَّد بعد','راجع المسقط الأرضي ووحدة الرسم ومعيار الطبقات أولًا.','!'):''}
  <form id="buildingForm"><div class="building-layout"><div class="card card-pad"><div class="card-head"><div><h2 class="card-title">عدد الأدوار وارتفاعاتها</h2><div class="card-subtitle">عدد الأدوار فوق الأرض يشمل الدور الأرضي.</div></div><span class="badge teal">إعداد المبنى</span></div>
  <div class="form-grid"><div class="field"><label>عدد الأدوار فوق الأرض (شامل الأرضي)</label><input class="control" id="storyCount" type="number" name="above_ground_story_count" min="1" max="100" value="${cfg.above_ground_story_count||4}" required><span class="field-help">مثال: ٤ أدوار = أرضي + ٣ متكرر.</span></div><div class="field"><label>ارتفاع الدور الأرضي (متر)</label><input class="control" type="number" name="ground_story_height_m" min="2" max="20" step="0.05" value="${cfg.ground_story_height_m||4.2}" required></div><div class="field"><label>ارتفاعات الأدوار العليا</label><select class="control" id="heightMode" name="typical_height_mode"><option value="uniform" ${cfg.upper_story_height_mode!=='individual'?'selected':''}>كلها بنفس الارتفاع</option><option value="individual" ${cfg.upper_story_height_mode==='individual'?'selected':''}>ارتفاع مختلف لكل دور</option></select></div><div class="field" id="typicalHeightWrap"><label>ارتفاع الدور المتكرر (متر)</label><input class="control" type="number" name="typical_story_height_m" min="2" max="20" step="0.05" value="${cfg.typical_story_height_m||3.2}"></div></div>
  <div id="individualHeights" class="form-grid hidden" style="margin-top:13px"></div>
  ${typicalMissing && Number(cfg.above_ground_story_count||4)>1 ? `<div class="notice warn" style="margin-top:13px"><span class="notice-icon">!</span><div><strong>لم ترفع مسقط المتكرر</strong><div>لازم ترفع المسقط أو تؤكد صراحة أن الأرضي مرجع مؤقت للمتكرر.</div><label class="checkline" style="margin-top:7px"><input id="confirmGroundTypical" type="checkbox"> أوافق على استخدام الأرضي كمرجع مؤقت للمتكرر للمراجعة فقط.</label></div></div>`:''}
  <div class="divider"></div><div class="section-heading" style="margin-top:0"><div><h2>مناسيب المبنى</h2><p>كل المناسيب محسوبة من مرجع الشارع الذي تحدده.</p></div></div><div class="form-grid"><div class="field"><label>منسوب مرجع الشارع (م)</label><input class="control" type="number" step="0.01" name="street_datum_elevation_m" value="${cfg.street_datum_elevation_m??0}"></div><div class="field"><label>تشطيب الأرضي أعلى الشارع (+م) أو أسفله (-م)</label><input class="control" type="number" step="0.01" name="ground_finished_floor_offset_from_street_m" value="${cfg.ground_finished_floor_offset_from_street_m??0.45}"></div></div>
  <div class="divider"></div><div class="section-heading" style="margin-top:0"><div><h2>البدروم والسطح</h2><p>لو مفيش مسقط مستقل، لازم تأكد استعمال مرجع مؤقت وتراجع حدوده.</p></div></div><label class="checkline"><input id="basementEnabled" type="checkbox" ${cfg.basement_enabled?'checked':''}> يوجد بدروم</label><div id="basementFields" class="form-grid ${cfg.basement_enabled?'':'hidden'}" style="margin-top:12px"><div class="field"><label>عدد أدوار البدروم</label><input class="control" type="number" id="basementCount" min="1" max="10" value="${cfg.basement_count||1}"></div><div class="field"><label>ارتفاع البدروم (متر)</label><input class="control" type="number" id="basementHeight" min="2" max="12" step="0.05" value="${(cfg.basement_story_heights_m||[])[0]||3.2}"></div>${basementMissing?`<label class="checkline"><input id="confirmGroundBasement" type="checkbox"> أوافق على استخدام بصمة الأرضي كمرجع حجمي مؤقت للبدروم؛ هذا لا يمثل حوائط السند أو التربة والمياه.</label>`:''}</div>
  ${roofMissing?`<div class="notice warn" style="margin-top:12px"><span class="notice-icon">!</span><div><strong>مسقط السطح غير مرفوع</strong><div>راجع ما إذا كانت غرف السطح والخزانات والفتحات مختلفة قبل استخدام المتكرر كمرجع.</div><label class="checkline" style="margin-top:7px"><input id="confirmTypicalRoof" type="checkbox" ${cfg.roof_plan_mode==='typical_proxy'?'checked':''}> أوافق على استخدام المتكرر مرجعًا مؤقتًا للسطح للمراجعة فقط.</label></div></div>`:''}
  <details class="advanced-details" style="margin-top:14px"><summary class="advanced-toggle">بيانات هندسية متقدمة (اختيارية الآن) <span>＋</span></summary><div class="form-grid" style="margin-top:12px"><div class="field"><label>مرشح نظام الأساسات</label><select class="control" name="foundation_system_candidate"><option value="not_selected">غير محدد</option><option value="isolated_footings_candidate">قواعد منفصلة — مرشح</option><option value="combined_footings_candidate">قواعد مشتركة — مرشح</option><option value="strip_footings_candidate">قواعد شريطية — مرشح</option><option value="raft_candidate">لبشة — مرشح</option><option value="piles_candidate">خوازيق — مرشح</option></select></div><div class="field"><label>تصنيف الموقع الزلزالي/التربة (لو معروف)</label><select class="control" name="site_class"><option value="unknown">غير محدد</option><option value="A">A</option><option value="B">B</option><option value="C">C</option><option value="D">D</option><option value="E">E</option></select></div><div class="field"><label>توصيات تقرير التربة</label><textarea class="control" name="geotechnical_notes" rows="2">${esc(p.project?.soil_notes||cfg.geotechnical_notes||'')}</textarea></div><div class="field"><label>مصدر الأحمال الحية</label><textarea class="control" name="occupancy_load_basis" rows="2">${esc(cfg.occupancy_load_basis||'')}</textarea></div><div class="field"><label>أساس الرياح</label><textarea class="control" name="wind_basis" rows="2">${esc(cfg.wind_basis||p.project?.wind_basis||'')}</textarea></div><div class="field"><label>أساس الزلازل</label><textarea class="control" name="seismic_basis" rows="2">${esc(cfg.seismic_basis||p.project?.seismic_basis||'')}</textarea></div></div></details>
  <div class="step-footer"><span class="hint">هذه الخطوة تنشئ هندسة مرشحة فقط؛ لا تشغّل تصميمًا إنشائيًا تلقائيًا.</span><div class="right-actions"><button class="btn btn-primary" type="submit" ${!p.plans_reviewed?'disabled':''}>كوّن النموذج للمراجعة ←</button></div></div></div>
  <aside><div class="card card-pad"><div class="card-head"><div><h2 class="card-title">المراجع المتاحة</h2><div class="card-subtitle">المساقط التي تم رفعها للبرنامج.</div></div></div>${Object.entries(p.plans||{}).map(([k,v])=>`<div class="result-link" style="margin-bottom:7px"><div class="result-file-icon">▧</div><div><strong>${esc(FLOOR_LABELS[k])}</strong><span>${esc(v.filename)} · ${fmt(v.entity_count)} عنصر</span></div><span class="badge green">جاهز</span></div>`).join('')||'<div class="field-help">لم يتم رفع مساقط.</div>'}<div class="divider"></div><div class="notice info"><span class="notice-icon">ⓘ</span><div>سيكرر البرنامج المتكرر بعدد الأدوار المحدد. أي اختلاف في الأعمدة أو الحوائط يجب أن يكون في المسقط المناظر أو يراجع يدويًا.</div></div></div></aside></div></form>
  ${p.building?renderBuildingSummary(p.building):''}`;
}
function renderBuildingSummary(b) {
  const levels=b.levels||[]; const issues=[...(b.critical_missing_inputs||[]),...(b.warnings||[])];
  return `<section class="card card-pad" style="margin-top:15px"><div class="review-head"><div><div class="eyebrow">CANDIDATE MODEL</div><h2 class="card-title">مسودة المبنى الناتجة</h2><div class="card-subtitle">راجع الرسم والمناسيب. هذا نموذج هندسي مرشح وليس نموذج تحليل معتمدًا.</div></div><span class="badge amber">مسودة للمراجعة</span></div><div class="review-metrics" style="margin-top:14px"><div class="review-metric"><span>المستويات</span><strong>${fmt(b.counts?.plan_levels_including_basement_and_roof)}</strong><small>بدروم / أرضي / أدوار / سطح</small></div><div class="review-metric"><span>مقاطع الأعمدة</span><strong>${fmt(b.counts?.column_segments)}</strong><small>مرشحة رأسيًا</small></div><div class="review-metric"><span>نواقص حرجة</span><strong>${fmt((b.critical_missing_inputs||[]).length)}</strong><small>تحتاج حسمًا</small></div></div>${b.preview_data_url?`<img class="model-preview" style="margin-top:13px;max-height:400px" src="${b.preview_data_url}" alt="معاينة نموذج المبنى">`:''}<div class="section-heading"><div><h2>جدول الأدوار</h2><p>المناسيب المقترحة من جدول الارتفاعات.</p></div></div><div style="overflow-x:auto"><table class="levels-table"><thead><tr><th>الدور</th><th>المنسوب (م)</th><th>مصدر المسقط</th><th>الحالة</th></tr></thead><tbody>${levels.map(l=>`<tr><td>${esc(l.label_ar||l.floor_id||'—')}</td><td>${fmt(l.elevation_m,3)}</td><td>${l.proxy_plan?'مرجع مؤقت':esc(l.source_filename||'غير محدد')}</td><td><span class="badge amber">مراجعة</span></td></tr>`).join('')}</tbody></table></div>${issues.length?`<div class="section-heading"><div><h2>النواقص والتحذيرات</h2><p>لا تنتقل للتحليل قبل مراجعة هذه النقاط.</p></div></div><div class="warning-list">${issues.slice(0,15).map(x=>`<div class="warning-item">${esc(x)}</div>`).join('')}</div>`:''}<div class="step-footer"><span class="hint">مطلوب: مراجعة مهندس قبل التحليل أو التصميم.</span><div class="right-actions"><a class="btn btn-outline" href="/api/download/building.zip">تنزيل حزمة المراجعة ZIP ↓</a><button class="btn btn-primary" data-go="review">افتح ملخص المراجعة ←</button></div></div></section>`;
}
function renderReview() {
  const b=state.workspace?.building; const p=state.workspace?.project||{}; const plans=state.workspace?.plans||{};
  if(!b) return `${pageHead('المرحلة ٤ من ٤','مراجعة النموذج','هنا تظهر المسودة والنواقص والملفات الناتجة. لو لم تكوّن النموذج بعد، ارجع لخطوة الأدوار والمناسيب.')} ${emptyState('◈','لا يوجد نموذج للمراجعة بعد','ارفع المساقط، أكد قراءتها، ثم أدخل عدد الأدوار والمناسيب لتكوين مسودة المبنى.','اذهب لتكوين المبنى','building')}`;
  const blockers=b.critical_missing_inputs||[]; const warnings=b.warnings||[]; const levels=b.levels||[];
  return `${pageHead('مراجعة قبل التحليل','ملخص النموذج الهندسي','راجع ما أدخله البرنامج، والمعلومات التي ما زالت ناقصة. لا يبدأ التحليل لمجرد إنشاء المسودة.','<a class="btn btn-outline" href="/api/download/building.zip">تنزيل حزمة المراجعة ZIP ↓</a>')}
    ${notice('warn','هذه مسودة هندسية وليست تصميمًا معتمدًا','فحص الاتصال وتكوين المستويات لا يثبتان صحة النظام الإنشائي أو الأحمال. التصميم والتسليح طبقًا للكود المصري غير مكتملين.','!')}
    <div class="card card-pad" style="margin-top:14px"><div class="review-head"><div><div class="eyebrow">PROJECT REVIEW</div><h2 class="card-title">${esc(p.name||'مشروع جديد')}</h2><div class="card-subtitle">${esc(p.location||'الموقع غير محدد')} · ${esc(p.use||'الاستخدام غير محدد')}</div></div><span class="badge amber">NOT FOR CONSTRUCTION</span></div>
    <div class="review-metrics" style="margin-top:15px"><div class="review-metric"><span>المستويات</span><strong>${fmt(b.counts?.plan_levels_including_basement_and_roof)}</strong><small>مستويات نموذجية</small></div><div class="review-metric"><span>مقاطع الأعمدة</span><strong>${fmt(b.counts?.column_segments)}</strong><small>عناصر مرشحة</small></div><div class="review-metric"><span>مساقط المصدر</span><strong>${Object.keys(plans).length}</strong><small>ملفات DXF</small></div></div>
    ${b.preview_data_url?`<img class="model-preview" style="margin-top:14px;max-height:440px" src="${b.preview_data_url}" alt="مسودة نموذج المبنى">`:''}
    <div class="section-heading"><div><h2>الأدوار ومصادرها</h2><p>أي مرجع مؤقت يظل ظاهرًا ولا يتحول إلى حقيقة ضمنية.</p></div></div><div style="overflow:auto"><table class="levels-table"><thead><tr><th>الدور</th><th>المنسوب</th><th>المسقط</th><th>المراجعة</th></tr></thead><tbody>${levels.map(l=>`<tr><td>${esc(l.label_ar||l.floor_id)}</td><td>${fmt(l.elevation_m,3)} م</td><td>${l.proxy_plan?'مرجع مؤقت':esc(l.source_filename||'—')}</td><td><span class="badge amber">لم يعتمد</span></td></tr>`).join('')}</tbody></table></div>
    <div class="section-heading"><div><h2>قائمة الموانع</h2><p>المعلومات التي يجب حسمها قبل الانتقال من الهندسة إلى التحليل.</p></div><span class="badge ${blockers.length?'amber':'green'}">${blockers.length} مانع</span></div>${blockers.length?`<div class="warning-list">${blockers.map(x=>`<div class="warning-item">${esc(x)}</div>`).join('')}</div>`:notice('success','لا توجد موانع مسجلة في هذه المرحلة','هذا لا يعني أن النموذج مؤهل للتحليل أو التصميم؛ ما زالت فحوص النموذج والتحليل مطلوبة.','✓')}
    ${warnings.length?`<details style="margin-top:13px"><summary class="advanced-toggle">تحذيرات إضافية (${warnings.length})</summary><div class="warning-list">${warnings.map(x=>`<div class="warning-item">${esc(x)}</div>`).join('')}</div></details>`:''}
    <div class="step-footer"><span class="hint">يمكنك الرجوع لتعديل الارتفاعات أو استبدال مسقط ثم إعادة إنشاء المسودة.</span><div class="right-actions"><button class="btn btn-outline" data-go="building">تعديل الأدوار</button><a class="btn btn-primary" href="/api/download/building.zip">تنزيل ملفات المراجعة ←</a></div></div></div>
    <div class="section-heading"><div><h2>مخرجات متاحة</h2><p>ملفات توثيقية للمراجعة فقط.</p></div></div><div class="overview-grid"><a class="result-link" href="/api/download/building.zip"><div class="result-file-icon">ZIP</div><div><strong>حزمة نموذج المبنى</strong><span>مصادر DXF وبيانات النموذج ومعاينة هندسية</span></div><span class="result-arrow">↓</span></a><div class="result-link"><div class="result-file-icon">AI</div><div><strong>مراجعة الوكيل</strong><span>${aiReady()?'النموذج المحلي اختُبر ويستطيع بدء المحادثة':'اختبر Ollama في لوحة المساعد على يمين الشاشة'}</span></div><button class="btn btn-outline btn-small" id="focusAiBtn">افتح المساعد</button></div></div>`;
}
function render() {
  updateChrome();
  const root=$('viewRoot');
  if(state.view==='home') root.innerHTML=renderHome();
  else if(state.view==='project') root.innerHTML=renderProject();
  else if(state.view==='plans') root.innerHTML=renderPlans();
  else if(state.view==='building') root.innerHTML=renderBuilding();
  else root.innerHTML=renderReview();
  bindViewEvents();
  $('chatMessages').innerHTML=renderChat();
  $('sendChatBtn').disabled=!aiReady(); $('chatState').textContent=aiReady()?`متصل · ${state.ai.chosen_model||''}`:'اختبر اتصال النموذج لبدء المحادثة';
  updateCopilotStatus();
}
function renderChat() {
  if(!state.chat.length) return `<div class="chat-welcome"><div class="welcome-symbol">✦</div><strong>أهلًا، أنا مساعد المشروع.</strong><p>اسألني عن المسقط أو بيانات المبنى. سأفحص المعلومات المتاحة وأوضح ما أعرفه وما يحتاج تأكيدًا.</p><div class="suggestion-list"><button class="suggestion" data-prompt="راجع حالة المشروع الحالي وحدد أهم البيانات الناقصة قبل تكوين النموذج.">ما البيانات الناقصة؟ <span>↗</span></button><button class="suggestion" data-prompt="راجع طبقات ومسقط الدور الأرضي ووضح ما فهمه البرنامج وما يحتاج تأكيدًا.">راجع المسقط المعماري <span>↗</span></button><button class="suggestion" data-prompt="اشرح لي الخطوة التالية في المشروع بلغة بسيطة.">ما الخطوة التالية؟ <span>↗</span></button></div></div>`;
  return state.chat.map(m=>`<div class="chat-message ${m.role==='user'?'user':'assistant'}"><span class="message-role">${m.role==='user'?'أنت':'المهندس المساعد'}</span>${esc(m.content)}</div>`).join('');
}
function traceLabel(name) {
  const map={inspect_project_status:'مراجعة بيانات المشروع',inspect_uploaded_dxf:'قراءة ملف DXF',inspect_multistorey_building_context:'فحص الأدوار والمناسيب',preflight_building_model_connectivity:'فحص اتصال العناصر',infer_dxf_structural_geometry:'استخراج هندسة الرسم',list_structural_system_options:'مقارنة الأنظمة الإنشائية',propose_structural_scheme_from_reviewed_dxf:'إنشاء مسودة هندسية',recommend_structural_system_from_reviewed_dxf:'ترشيح نظام بواسطة AI'};
  return map[name]||name||'أداة هندسية';
}
function traceSummaryLines(summary) {
  if(!summary||typeof summary!=='object') return [];
  const labels={tool_status:'نتيجة الأداة',status:'الحالة',reason:'السبب',required_user_action:'المطلوب منك',candidate_status:'حالة المسودة',candidate_review_basis:'أساس المراجعة',entity_roles_individually_reviewed:'مراجعة العناصر واحدًا واحدًا',plan_title_candidate:'عنوان اللوحة المقروء',candidate_counts:'أعداد العناصر المرشحة',counts:'ملخص الأعداد',critical_gaps:'النواقص',gap_count:'عدد النواقص',critical_missing_inputs:'بيانات ناقصة',config_errors:'أخطاء الإعداد',config_warnings:'تحذيرات الإعداد',analysis_gate:'بوابة التحليل',automatic_analysis_allowed:'السماح بالتحليل التلقائي',design_status:'حالة التصميم',system_id:'معرف النظام المرشح',system_name_ar:'النظام المرشح',rationale:'سبب الترشيح',alternatives:'بدائل',based_on_observations:'أدلة مستخدمة',assumptions:'افتراضات',missing_inputs:'مدخلات ناقصة',warnings:'تحذيرات',critical_model_gaps:'فجوات النموذج',entity_count:'عدد كيانات CAD',layer_count:'عدد الطبقات',role_counts:'العناصر حسب النوع',required_review:'مراجعات مطلوبة',summary_truncated:'ملخص مختصر'};
  return Object.entries(summary).map(([k,v])=>`${labels[k]||k}: ${typeof v==='string'?v:JSON.stringify(v)}`).slice(0,10);
}
function renderAgentTrace(items) {
  if(!items||!items.length) return '';
  return `<div class="trace-header"><strong>إيه اللي الوكيل عمله فعلًا؟</strong><span>${items.length} خطوة</span></div>${items.map((t,i)=>{
    const label=traceLabel(t.name||t.tool);const status=t.status||'تم';const lines=traceSummaryLines(t.summary||t.result_summary);
    return `<details class="trace-step" ${i===items.length-1?'open':''}><summary><span class="trace-num">${i+1}</span><span class="trace-name">${esc(label)}</span><span class="trace-status ${String(status).includes('BLOCKED')||String(status).includes('ERROR')?'warn':'ok'}">${esc(status)}</span></summary><div class="trace-detail">${t.error?`<div class="trace-error">${esc(t.error)}</div>`:''}${lines.length?`<ul>${lines.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:'<p>لا توجد تفاصيل إضافية من هذه الأداة.</p>'}</div></details>`;
  }).join('')}`;
}
function updateCopilotStatus() {
  const title=$('aiConnectionTitle'),desc=$('aiConnectionDesc'),controls=$('aiModelControls'),btn=$('checkAiBtn'),dot=$('aiConnectionDot');
  if(aiReady()) {title.textContent='النموذج جاهز للرد';desc.textContent=`تم اختبار رد حقيقي من ${state.ai.chosen_model}. تقدر تسأل عن المشروع.`;dot.className='connection-indicator good';controls.classList.remove('hidden');btn.textContent='تحديث قائمة النماذج';}
  else if(state.ai.reachable) {title.textContent='Ollama يعمل — الرد غير مختبر';desc.textContent='اختَر نموذجًا محليًا واضغط «اختبار رد حقيقي» قبل بدء المحادثة.';dot.className='connection-indicator bad';controls.classList.remove('hidden');btn.textContent='تحديث قائمة النماذج';}
  else {title.textContent='المساعد غير متصل';desc.textContent=state.ai.error||'شغّل Ollama ثم نزّل نموذجًا محليًا. لن نعرض المساعد كمتصل قبل نجاح رد حقيقي.';dot.className='connection-indicator';controls.classList.add('hidden');btn.textContent='فحص الاتصال بالنموذج';}
  const test=$('aiTestResult'); if(state.ai.testMessage){test.classList.remove('hidden');test.textContent=state.ai.testMessage;test.className='ai-test-result '+(aiReady()?'':'error');} else test.classList.add('hidden');
  $('sendChatBtn').disabled=!aiReady(); $('chatState').textContent=aiReady()?`متصل · ${state.ai.chosen_model}`:'اختبر اتصال النموذج لبدء المحادثة';
}
function bindViewEvents() {
  document.querySelectorAll('[data-go]').forEach(btn=>btn.addEventListener('click',()=>go(btn.dataset.go)));
  const projectForm=$('projectForm'); if(projectForm) projectForm.addEventListener('submit',saveProject);
  const unit=$('drawingUnits');if(unit)unit.addEventListener('change',e=>state.selectedUnits=e.target.value);
  document.querySelectorAll('[data-upload-floor]').forEach(input=>input.addEventListener('change',()=>{if(input.files?.[0])uploadPlan(input.dataset.uploadFloor,input.files[0]);}));
  document.querySelectorAll('[data-delete-plan]').forEach(btn=>btn.addEventListener('click',()=>deletePlan(btn.dataset.deletePlan)));
  const confirmBtn=$('confirmPlansBtn'); if(confirmBtn)confirmBtn.addEventListener('click',confirmPlans);
  const buildingForm=$('buildingForm');if(buildingForm){buildingForm.addEventListener('submit',createBuilding); $('heightMode').addEventListener('change',toggleHeightMode); $('storyCount').addEventListener('change',renderIndividualHeightFields); $('basementEnabled').addEventListener('change',()=> $('basementFields').classList.toggle('hidden',!$('basementEnabled').checked));toggleHeightMode();}
  $('focusAiBtn')?.addEventListener('click',()=>{$('chatInput').focus(); $('copilotPanel').scrollIntoView({behavior:'smooth',block:'start'});});
  document.querySelectorAll('[data-prompt]').forEach(btn=>btn.addEventListener('click',()=>{$('chatInput').value=btn.dataset.prompt; if(aiReady())sendChat(); else toast('اختبر النموذج المحلي أولًا من لوحة المساعد.','error');}));
}
async function saveProject(event) {
  event.preventDefault();const f=new FormData(event.currentTarget);const payload=Object.fromEntries(f.entries());payload.fc=Number(payload.fc||30);payload.fy=Number(payload.fy||420);
  try{setLoading(true,'حفظ بيانات المشروع','بنحفظ بياناتك محليًا على الجهاز.');const out=await api('/api/project',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});await loadWorkspace();go('plans');toast(out.message,'success');}catch(e){toast(e.message,'error');}finally{setLoading(false);}
}
async function uploadPlan(floor,file) {
  if(!$('confirmLayerStandard')?.checked){toast('أكد وحدة الرسم ومعيار الطبقات أولًا.','error');return;}
  const form=new FormData();form.append('file',file);form.append('units',state.selectedUnits);form.append('confirm_layer_standard','true');
  try{setLoading(true,`قراءة ${FLOOR_LABELS[floor]}`,'نقرأ هندسة الملف والطبقات ونجهز معاينة للمراجعة.');const res=await api(`/api/plans/${floor}`,{method:'POST',body:form});await loadWorkspace();render();toast(res.message,'success');}
  catch(e){toast(e.message,'error');}finally{setLoading(false);}
}
async function deletePlan(floor) { if(!confirm(`هل تريد إزالة ${FLOOR_LABELS[floor]} من مساحة العمل؟`))return;try{await api(`/api/plans/${floor}`,{method:'DELETE'});await loadWorkspace();render();toast('تمت إزالة المسقط.','success');}catch(e){toast(e.message,'error');} }
async function confirmPlans() {
  if(!$('confirmLayerStandard')?.checked){toast('أكد معيار الطبقات ووحدة الرسم.','error');return;}
  if(!$('confirmPlanReview')?.checked){toast('راجع المعاينة ثم فعّل مربع التأكيد.','error');return;}
  try{const r=await api('/api/plans/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm_units:true,confirm_layer_standard:true,confirm_manual_review:true})});await loadWorkspace();render();toast(r.message,'success');go('building');}catch(e){toast(e.message,'error');}
}
function toggleHeightMode() { const mode=$('heightMode')?.value; $('typicalHeightWrap')?.classList.toggle('hidden',mode==='individual'); $('individualHeights')?.classList.toggle('hidden',mode!=='individual'); if(mode==='individual')renderIndividualHeightFields(); }
function renderIndividualHeightFields() {
  const wrap=$('individualHeights'); if(!wrap || $('heightMode').value!=='individual')return;
  const n=Math.max(0,Math.min(99,Number($('storyCount').value||1)-1)); const old=[...wrap.querySelectorAll('input')].map(x=>x.value);wrap.innerHTML=Array.from({length:n},(_,i)=>`<div class="field"><label>ارتفاع الدور ${i+2} (متر)</label><input class="control" type="number" name="upper_h_${i}" min="2" max="20" step="0.05" value="${old[i]||3.2}" required></div>`).join('');
}
async function createBuilding(event) {
  event.preventDefault();const f=new FormData(event.currentTarget);const raw=Object.fromEntries(f.entries());const storyCount=Number(raw.above_ground_story_count||0);const variable=raw.typical_height_mode==='individual';
  const payload={above_ground_story_count:storyCount,ground_story_height_m:Number(raw.ground_story_height_m),typical_height_mode:raw.typical_height_mode,typical_story_height_m:Number(raw.typical_story_height_m||3.2),upper_story_heights_m:variable?Array.from({length:Math.max(0,storyCount-1)},(_,i)=>Number(f.get(`upper_h_${i}`))):[],street_datum_elevation_m:Number(raw.street_datum_elevation_m||0),ground_finished_floor_offset_from_street_m:Number(raw.ground_finished_floor_offset_from_street_m||0),confirm_ground_as_typical:$('confirmGroundTypical')?.checked||false,basement_enabled:$('basementEnabled').checked,basement_count:Number($('basementCount')?.value||1),basement_height_m:Number($('basementHeight')?.value||3.2),confirm_ground_as_basement:$('confirmGroundBasement')?.checked||false,confirm_typical_as_roof:$('confirmTypicalRoof')?.checked||false,foundation_system_candidate:raw.foundation_system_candidate||'not_selected',site_class:raw.site_class||'unknown',geotechnical_notes:raw.geotechnical_notes||'',occupancy_load_basis:raw.occupancy_load_basis||'',wind_basis:raw.wind_basis||'',seismic_basis:raw.seismic_basis||'',concrete_strength_mpa:Number(state.workspace?.project?.fc||30),steel_yield_strength_mpa:Number(state.workspace?.project?.fy||420)};
  try{setLoading(true,'تكوين مسودة المبنى','نكرر المساقط على المناسيب ونراجع البيانات الأساسية.');const res=await api('/api/building/candidate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});await loadWorkspace();render();toast(res.message,'success');setTimeout(()=>go('review'),250);}catch(e){toast(e.message,'error');}finally{setLoading(false);}
}
async function checkAI() {
  try{setLoading(true,'فحص Ollama المحلي','نبحث عن النماذج المثبتة على جهازك.');const r=await api('/api/ai/status');state.ai.reachable=r.reachable;state.ai.models=r.models||[];state.ai.error=r.error||'';state.ai.tested=Boolean(r.tested);state.ai.tested_model=r.tested_model;state.ai.chosen_model=(r.recommended_model&&state.ai.models.includes(r.recommended_model)&&!state.ai.tested)?r.recommended_model:(r.chosen_model&&state.ai.models.includes(r.chosen_model)?r.chosen_model:(r.recommended_model||state.ai.models[0]||''));if(state.ai.models.length){const pick=$('aiModelSelect');pick.innerHTML=state.ai.models.map(m=>`<option value="${esc(m)}" ${m===state.ai.chosen_model?'selected':''}>${esc(m)}</option>`).join('');}updateCopilotStatus();toast(r.reachable?`Ollama متصل. النماذج المتاحة: ${r.models.length}.`:'لم نصل إلى Ollama. راجع الرسالة داخل المساعد.',r.reachable?'success':'error');}
  catch(e){state.ai.reachable=false;state.ai.error=e.message;updateCopilotStatus();toast(e.message,'error');}finally{setLoading(false);}
}
async function testAI() {
  const model=$('aiModelSelect')?.value;if(!model){toast('لم يتم العثور على نموذج محلي.','error');return;}
  try{setLoading(true,'اختبار رد الذكاء الاصطناعي','نرسل سؤالًا حقيقيًا للنموذج. قد يأخذ أول رد بعض الوقت.');const r=await api('/api/ai/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model})});state.ai.reachable=true;state.ai.chosen_model=model;state.ai.tested=Boolean(r.ok);state.ai.tested_model=r.ok?model:'';state.ai.testMessage=r.ok?r.answer:r.error;updateCopilotStatus();if(r.ok)toast('نجح الرد النصي واستدعاء الأداة. الوكيل جاهز.','success');else toast(r.message,'error');}
  catch(e){state.ai.tested=false;state.ai.testMessage=e.message;updateCopilotStatus();toast(e.message,'error');}finally{setLoading(false);}
}
async function sendChat() {
  const input=$('chatInput');const message=input.value.trim();if(!message)return;if(!aiReady()){toast('اختبر رد النموذج قبل بدء المحادثة.','error');return;}
  state.chat.push({role:'user',content:message});input.value='';$('chatMessages').innerHTML=renderChat();$('chatMessages').scrollTop=$('chatMessages').scrollHeight;setLoading(true,'الوكيل يراجع طلبك','قد يستدعي أدوات فحص ثم يقرأ نتائجها.');$('sendChatBtn').disabled=true;
  try{const r=await api('/api/ai/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,model:state.ai.chosen_model})});state.chat.push({role:'assistant',content:r.answer});state.lastTrace=r.tools||[];$('agentTrace').classList.toggle('hidden',!state.lastTrace.length);$('agentTrace').innerHTML=renderAgentTrace(state.lastTrace);}
  catch(e){state.chat.push({role:'assistant',content:`تعذر إكمال الطلب: ${e.message}\n\nتأكد أن Ollama يعمل وأن النموذج المختار يدعم استدعاء الأدوات.`});}
  finally{setLoading(false);$('chatMessages').innerHTML=renderChat();$('chatMessages').scrollTop=$('chatMessages').scrollHeight;$('sendChatBtn').disabled=!aiReady();}
}
async function loadWorkspace() {
  const w=await api('/api/workspace');state.workspace=w;
  const history=await api('/api/ai/history').catch(()=>({messages:[],trace:[]}));state.chat=history.messages||[];state.lastTrace=[];
  const last=history.last_result;if(last?.tool_results_summary?.length)state.lastTrace=last.tool_results_summary;else if(history.trace?.length)state.lastTrace=history.trace;
  if(state.lastTrace.length){$('agentTrace').classList.remove('hidden');$('agentTrace').innerHTML=renderAgentTrace(state.lastTrace);}
  $('sideProjectName').textContent=w.project?.name||'مشروع جديد';$('sideProjectLocation').textContent=w.project?.location||'لم تحفظ بيانات المشروع';
  if(w.plans_units)state.selectedUnits=w.plans_units;
  if(w.ai?.tested){state.ai.tested=true;state.ai.tested_model=w.ai.model;state.ai.chosen_model=w.ai.model;state.ai.testMessage=w.ai.text;}
  render();
}

document.querySelectorAll('.nav-item').forEach(btn=>btn.addEventListener('click',()=>go(btn.dataset.view)));
document.addEventListener('click', e=>{const suggestion=e.target.closest('[data-prompt]');if(suggestion){e.preventDefault();$('chatInput').value=suggestion.dataset.prompt;if(aiReady())sendChat();else toast('اختبر النموذج المحلي أولًا من لوحة المساعد.','error');}});
$('refreshBtn').addEventListener('click',async()=>{try{await loadWorkspace();await checkAI();toast('تم تحديث حالة مساحة العمل.','success');}catch(e){toast(e.message,'error');}});
$('checkAiBtn').addEventListener('click',checkAI);
$('testAiBtn').addEventListener('click',testAI);
$('aiModelSelect').addEventListener('change',()=>{state.ai.chosen_model=$('aiModelSelect').value;state.ai.tested=false;updateCopilotStatus();});
$('chatForm').addEventListener('submit',e=>{e.preventDefault();sendChat();});
$('chatInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendChat();}});
$('clearChatBtn').addEventListener('click',()=>{if(!confirm('مسح المحادثة الظاهرة؟'))return;state.chat=[];$('agentTrace').classList.add('hidden');$('chatMessages').innerHTML=renderChat();});
$('collapseCopilot').addEventListener('click',()=>{const panel=$('copilotPanel');const collapsed=panel.classList.toggle('collapsed');document.querySelector('.workspace-body').classList.toggle('assistant-collapsed',collapsed);$('collapseCopilot').textContent=collapsed?'↙':'↗';$('collapseCopilot').title=collapsed?'إظهار المساعد':'إخفاء المساعد';});

(async()=>{try{await loadWorkspace();if(state.workspace?.startup_warning)toast(state.workspace.startup_warning,'error');}catch(e){toast(`تعذر تحميل مساحة العمل: ${e.message}`,'error');$('viewRoot').innerHTML=notice('error','تعذر الاتصال بالخادم المحلي','أغلق البرنامج وأعد تشغيل run_app.bat.');}})();
