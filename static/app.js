const state = {
  questions: [],
  dashboardQuestions: [],
  dashboardStats: [],
  dashboardSubjectStats: [],
  documents: [],
  stats: [],
  subjectStats: [],
  categories: [],
  chapters: [],
  subjects: [],
  view: "dashboard",
  category: "",
  status: "",
  documentId: "",
  subject: "",
  chapter: "",
  dashboardSubject: "",
  dashboardDocumentId: "",
  search: "",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const META_TAGS = ["计算失误", "公式遗忘", "逻辑死角", "题意理解偏差"];

document.body.dataset.view = state.view;

function typesetMath(root = document.body) {
  if (window.MathJax?.typesetPromise) {
    window.MathJax.typesetPromise([root]).catch(() => {});
  }
}

function statusClass(status) {
  if (status === "做错") return "wrong";
  if (status === "需复习" || status === "半会") return "review";
  return "";
}

function reviewTag(q) {
  if (!q.ever_wrong) return "";
  if (q.mastered_at) return `<span class="tag memory mastered">已掌握</span>`;
  if (q.next_review_at) return `<span class="tag memory">${q.retention_stage || q.review_stage || 0}天 · ${q.next_review_at}</span>`;
  return `<span class="tag memory">曾错题</span>`;
}

function selectedMetaTags() {
  return $$(".meta-check input:checked").map((input) => input.value);
}

function metaTagControls(selected = []) {
  return META_TAGS.map(
    (tag) => `
      <label class="meta-check">
        <input type="checkbox" value="${tag}" ${selected.includes(tag) ? "checked" : ""} />
        <span>${tag}</span>
      </label>`
  ).join("");
}

function documentLabel(doc) {
  const title = doc.title || doc.filename || "做题本";
  const kind = doc.document_kind || "做题本";
  return `${title} · ${kind}`;
}

function documentKind(doc) {
  return doc.document_kind || "做题本";
}

function questionKind(question) {
  return question.document_kind || "做题本";
}

function snippet(text) {
  const clean = (text || "这页 PDF 没有可提取文字，可直接查看题图并手动标注。").replace(/\s+/g, " ").trim();
  return clean.length > 86 ? `${clean.slice(0, 86)}...` : clean;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "请求失败");
  return data;
}

async function loadDocuments() {
  const data = await api("/api/documents");
  state.documents = data.documents;
  state.subjects = data.subjects;
  renderDocumentFilters();
  renderDocuments();
}

async function loadQuestions() {
  const params = new URLSearchParams();
  if (state.category) params.set("category", state.category);
  if (state.status) params.set("status", state.status);
  if (state.documentId) params.set("document_id", state.documentId);
  if (state.subject) params.set("subject", state.subject);
  if (state.chapter) params.set("chapter", state.chapter);
  if (state.search) params.set("search", state.search);
  const data = await api(`/api/questions?${params}`);
  state.questions = data.questions;
  state.stats = data.stats;
  state.subjectStats = data.subject_stats;
  state.categories = data.categories;
  state.chapters = data.chapters;
  state.subjects = data.subjects;
  renderAll();
}

async function refresh() {
  await loadDocuments();
  await loadDashboardData();
  await loadQuestions();
}

async function loadDashboardData() {
  const docs = dashboardDocuments().filter((doc) => !state.dashboardSubject || doc.subject === state.dashboardSubject);
  if (state.dashboardDocumentId && !docs.some((doc) => doc.id === state.dashboardDocumentId)) {
    state.dashboardDocumentId = "";
  }
  const params = new URLSearchParams();
  if (state.dashboardSubject) params.set("subject", state.dashboardSubject);
  if (state.dashboardDocumentId) params.set("document_id", state.dashboardDocumentId);
  const data = await api(`/api/questions?${params}`);
  state.dashboardQuestions = data.questions;
  state.dashboardStats = data.stats;
  state.dashboardSubjectStats = data.subject_stats;
  renderDashboardFilters();
  renderDashboard();
}

function renderAll() {
  renderQuestionFilters();
  renderDashboard();
  const regularQuestions = state.questions.filter((q) => questionKind(q) !== "模拟卷");
  const mockQuestions = state.questions.filter((q) => questionKind(q) === "模拟卷");
  $("#questionCountBadge").textContent = `${regularQuestions.length} 题`;
  $("#mockCountBadge").textContent = `${mockQuestions.length} 题`;
  renderQuestionGrid("#questionGrid", regularQuestions, "还没有题目。先从左侧上传 PDF，或清空筛选条件。");
  renderQuestionGrid("#mockQuestionGrid", mockQuestions, "还没有模拟卷题目。先上传整卷 PDF。");
  renderQuestionGrid("#mistakeGrid", state.questions.filter((q) => ["做错", "需复习", "半会"].includes(q.status)), "还没有错题。");
}

function renderDocumentFilters() {
  $("#subjectSuggestions").innerHTML = state.subjects.map((subject) => `<option value="${subject}"></option>`).join("");
  const chapterDocs = state.documents.filter((doc) => documentKind(doc) !== "模拟卷");
  $("#statsDocumentSelect").innerHTML = chapterDocs
    .map((doc) => `<option value="${doc.id}">${documentLabel(doc)}</option>`)
    .join("");
}

function firstUploadDocuments() {
  const sorted = [...state.documents].sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
  const seen = new Set();
  return sorted.filter((doc) => {
    const key = `${doc.subject}::${doc.document_kind || "做题本"}::${doc.title || doc.filename}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function dashboardDocuments() {
  return firstUploadDocuments().filter((doc) => documentKind(doc) !== "模拟卷");
}

function renderDashboardFilters() {
  $("#dashboardSubjectFilter").innerHTML = `<option value="">请选择科目</option>${state.subjects
    .map((subject) => `<option ${subject === state.dashboardSubject ? "selected" : ""}>${subject}</option>`)
    .join("")}`;
  const docs = dashboardDocuments().filter((doc) => !state.dashboardSubject || doc.subject === state.dashboardSubject);
  $("#dashboardDocumentFilter").innerHTML = `<option value="">请选择做题本</option>${docs
    .map((doc) => `<option value="${doc.id}" ${doc.id === state.dashboardDocumentId ? "selected" : ""}>${documentLabel(doc)}</option>`)
    .join("")}`;
}

function renderQuestionFilters() {
  const docs = state.documents.filter((doc) => !state.subject || doc.subject === state.subject);
  $("#documentFilter").innerHTML = `<option value="">全部资料</option>${docs
    .map((doc) => `<option value="${doc.id}" ${doc.id === state.documentId ? "selected" : ""}>${documentLabel(doc)}</option>`)
    .join("")}`;
  $("#subjectFilter").innerHTML = `<option value="">全部科目</option>${state.subjects
    .map((subject) => `<option ${subject === state.subject ? "selected" : ""}>${subject}</option>`)
    .join("")}`;
  $("#categoryFilter").innerHTML = `<option value="">全部知识点</option>${state.categories
    .map((category) => `<option ${category === state.category ? "selected" : ""}>${category}</option>`)
    .join("")}`;
  $("#chapterFilter").innerHTML = `<option value="">全部章节</option>${state.chapters
    .map((chapter) => `<option ${chapter === state.chapter ? "selected" : ""}>${chapter}</option>`)
    .join("")}`;
  $("#statusFilter").value = state.status;
}

function renderDashboard() {
  const dashboardReady = Boolean(state.dashboardSubject && state.dashboardDocumentId);
  const source = dashboardReady ? state.dashboardQuestions : [];
  const stats = dashboardReady ? state.dashboardStats : [];
  const total = source.length;
  const done = source.filter((q) => q.status && q.status !== "未做").length;
  const progress = total ? Math.round((done / total) * 100) : 0;
  const wrong = source.filter((q) => q.status === "做错").length;
  const review = source.filter((q) => ["需复习", "半会"].includes(q.status)).length;
  const weak = [...stats].sort((a, b) => (b.wrong || 0) - (a.wrong || 0))[0];

  $("#totalCount").textContent = total;
  if ($("#doneCount")) $("#doneCount").textContent = done;
  if ($("#progressRate")) $("#progressRate").textContent = `${progress}%`;
  if ($("#wrongCount")) $("#wrongCount").textContent = wrong;
  if ($("#reviewCount")) $("#reviewCount").textContent = review;
  if ($("#weakCategory")) {
    $("#weakCategory").textContent = dashboardReady ? (weak && weak.wrong ? weak.category : "暂无") : "请选择科目";
  }

  renderStats("#statsList", stats, "category", "选择科目和做题本后会显示对应知识点分布。");
  renderStats(
    "#subjectStatsList",
    dashboardReady ? state.dashboardSubjectStats : [],
    "subject",
    "选择科目和做题本后会显示科目分布。"
  );
}

function renderStats(target, stats, labelKey, emptyText) {
  const max = Math.max(...stats.map((item) => item.total), 1);
  $(target).innerHTML =
    stats
      .map(
        (item) => `
        <div class="stat-row">
          <strong>${item[labelKey]}</strong>
          <div class="bar"><span style="width: ${(item.total / max) * 100}%"></span></div>
          <span>${item.total} 题</span>
        </div>`
      )
      .join("") || `<p>${emptyText}</p>`;
}

function renderDocuments() {
  const books = state.documents.filter((doc) => documentKind(doc) !== "模拟卷");
  const mocks = state.documents.filter((doc) => documentKind(doc) === "模拟卷");
  renderDocumentGrid("#documentGrid", books, "还没有做题本。先在上方导入章节练习 PDF。");
  renderDocumentGrid("#mockDocumentGrid", mocks, "还没有模拟卷。先在上方导入整卷 PDF。");
}

function renderDocumentGrid(target, docs, emptyText) {
  const node = $(target);
  if (!node) return;
  node.innerHTML =
    docs
      .map((doc) => documentCard(doc))
      .join("") || `<p class="empty-note">${emptyText}</p>`;
}

function documentCard(doc) {
  const kind = documentKind(doc);
  const rescanLabel = kind === "模拟卷" ? "重扫整卷" : "重扫章节";
  return `
        <article class="document-card">
          <div>
            <h3>${doc.title || doc.filename}</h3>
            <p>${doc.subject} · ${kind} · ${doc.question_count || 0} 题 · 错题 ${doc.wrong_count || 0} · 需复习 ${doc.review_count || 0}</p>
            <span class="tag kind ${kind === "模拟卷" ? "mock" : "paper"}">${kind}</span>
            <p>${doc.filename}</p>
          </div>
          <div class="doc-actions">
            <button data-view-doc="${doc.id}">查看</button>
            <button class="ghost" data-edit-doc="${doc.id}">编辑</button>
            <button class="ghost" data-stats-doc="${doc.id}">统计</button>
            <button class="ghost" data-rescan-doc="${doc.id}">${rescanLabel}</button>
            <button class="danger" data-delete-doc="${doc.id}">删除</button>
          </div>
        </article>`;
}

async function editDocument(id) {
  const doc = state.documents.find((item) => item.id === id);
  if (!doc) return;
  const kind = documentKind(doc);
  const dialog = $("#detailDialog");
  $("#detailContent").innerHTML = `
    <form class="document-editor" id="documentEditForm">
      <div class="panel-head">
        <div>
          <h2>编辑${kind}</h2>
          <p>只修改显示名称和科目，不会影响已导入题目、错题和复习记录。</p>
        </div>
        <button type="button" class="ghost" id="closeDocumentEdit">关闭</button>
      </div>
      <label>
        资料名称
        <input id="editDocumentTitle" value="${doc.title || doc.filename || ""}" maxlength="120" required />
      </label>
      <label>
        科目/分类
        <input id="editDocumentSubject" value="${doc.subject || "未分类"}" maxlength="60" list="subjectSuggestions" />
      </label>
      <label>
        资料类型
        <select id="editDocumentKind">
          <option value="做题本" ${doc.document_kind !== "模拟卷" ? "selected" : ""}>做题本</option>
          <option value="模拟卷" ${doc.document_kind === "模拟卷" ? "selected" : ""}>模拟卷</option>
        </select>
      </label>
      <p class="edit-file-name">原始文件：${doc.filename}</p>
      <div class="detail-actions">
        <button type="submit">保存修改</button>
        <button type="button" class="ghost" id="cancelDocumentEdit">取消</button>
      </div>
    </form>`;
  dialog.showModal();
  $("#closeDocumentEdit").onclick = () => dialog.close();
  $("#cancelDocumentEdit").onclick = () => dialog.close();
  $("#documentEditForm").onsubmit = async (event) => {
    event.preventDefault();
    try {
      await api(`/api/documents/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: $("#editDocumentTitle").value.trim(),
          subject: $("#editDocumentSubject").value.trim() || "未分类",
          document_kind: $("#editDocumentKind").value,
        }),
      });
      dialog.close();
      await refresh();
    } catch (error) {
      alert(error.message);
    }
  };
}

function renderQuestionGrid(target, questions, emptyText = "还没有题目。先从左侧上传 PDF，或清空筛选条件。") {
  $(target).innerHTML =
    questions.length
      ? questions
          .map(
            (q) => `
        <article class="question-card">
          <div class="thumb" data-open="${q.id}">
            <img src="${q.image_url}" alt="第 ${q.page_number} 页题目" loading="lazy" />
          </div>
          <div class="card-body">
            <div class="meta">
              <span>${q.document_title || q.filename || "做题本"} · 第 ${q.page_number} 页</span>
              <span class="tag status ${statusClass(q.status)}">${q.status}</span>
            </div>
            <strong>${q.category}</strong>
            <span class="tag">${q.subject || "未分类"} · ${q.chapter || "未识别章节"}</span>
            <span class="tag kind ${questionKind(q) === "模拟卷" ? "mock" : "paper"}">${questionKind(q)}</span>
            ${reviewTag(q)}
            <p class="snippet">${snippet(q.ocr_text)}</p>
            <div class="actions">
              <button data-status="做对" data-id="${q.id}">做对</button>
              <button data-status="做错" data-id="${q.id}">做错</button>
              <button class="danger" data-delete-question="${q.id}">删除</button>
            </div>
          </div>
        </article>`
          )
          .join("")
      : `<p class="empty-note">${emptyText}</p>`;
}

async function updateQuestion(id, payload) {
  try {
    await api(`/api/questions/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
    await refresh();
  } catch (error) {
    alert(error.message);
    throw error;
  }
}

async function deleteQuestion(id) {
  if (!confirm("确定删除这道题吗？这个操作会移除题目记录和对应页面图片。")) return;
  const result = await api(`/api/questions/${id}`, { method: "DELETE" });
  if (result.document_deleted && result.document_id) {
    if (state.documentId === result.document_id) {
      state.documentId = "";
      state.category = "";
      state.chapter = "";
    }
    if (state.dashboardDocumentId === result.document_id) {
      state.dashboardDocumentId = "";
    }
  }
  await refresh();
}

async function deleteDocument(id) {
  const doc = state.documents.find((item) => item.id === id);
  const name = doc ? doc.title || doc.filename : "这套做题本";
  const kind = doc ? documentKind(doc) : "做题本";
  if (!confirm(`确定删除「${name}」吗？这会删除整套${kind}、题目记录和页面图片。`)) return;
  await api(`/api/documents/${id}`, { method: "DELETE" });
  if (state.documentId === id) {
    state.documentId = "";
    state.category = "";
    state.chapter = "";
  }
  if (state.dashboardDocumentId === id) state.dashboardDocumentId = "";
  await refresh();
}

async function rescanDocument(id) {
  const doc = state.documents.find((item) => item.id === id);
  const name = doc ? doc.title || doc.filename : "这套做题本";
  const kind = doc ? documentKind(doc) : "做题本";
  const scanLabel = kind === "模拟卷" ? "整卷" : "章节";
  if (!confirm(`重新扫描「${name}」的页眉/右上角${scanLabel}吗？这不会调用 AI，也不会消耗 token。`)) return;
  const result = await api(`/api/documents/${id}/rescan-chapters`, { method: "POST", body: "{}" });
  alert(`已重扫 ${result.pages} 页，更新 ${result.updated} 条题目记录。`);
  await refresh();
}

async function openDetail(id, presetStatus = "") {
  const q = await api(`/api/questions/${id}`);
  const currentStatus = presetStatus || q.status;
  const dialog = $("#detailDialog");
  $("#detailContent").innerHTML = `
    <div class="detail">
      <div class="detail-image">
        <div class="crop-toolbar">
          <button class="ghost" id="enableCrop">裁剪题目边界</button>
          <button id="saveCrop" disabled>保存裁剪</button>
        </div>
        <div class="crop-stage" id="cropStage">
          <img id="detailImage" src="${q.image_url}?t=${Date.now()}" alt="题目页面" />
          <div id="cropBox" class="crop-box hidden"></div>
        </div>
      </div>
      <div class="detail-side">
        <div class="panel-head">
          <div>
            <h2>${q.category}</h2>
            <p>${q.document_title || q.filename} · ${q.subject || "其他"} · 第 ${q.page_number} 页 · ${q.difficulty}</p>
          </div>
          <button class="ghost" id="closeDetail">关闭</button>
        </div>
        <label>
          章节
          <input id="detailChapter" value="${q.chapter || ""}" placeholder="例如：第3章 多元函数微分学" />
        </label>
        <label>
          状态
          <select id="detailStatus">
            ${["未做", "做对", "做错", "半会", "需复习"].map((s) => `<option ${s === currentStatus ? "selected" : ""}>${s}</option>`).join("")}
          </select>
        </label>
        <div class="memory-panel">
          <strong>复习记忆</strong>
          <span>${q.ever_wrong ? (q.mastered_at ? "已完成多轮复习，标记为已掌握。" : `保持阶段：${q.retention_stage || 1} 天，下次复习：${q.next_review_at || "待安排"}`) : "这道题还没有进入错题复习队列。"}</span>
          <small>created_at: ${q.created_at || "-"} · retention_stage: ${q.retention_stage || 0}</small>
        </div>
        <label>
          元认知错因
          <div class="meta-checks">${metaTagControls(q.meta_tags || [])}</div>
        </label>
        <label>
          我的备注
          <textarea id="userNote" placeholder="记录这题错在哪里，或者下次要注意什么">${q.user_note || ""}</textarea>
        </label>
        <div class="detail-actions">
          <button id="saveDetail">保存标注</button>
          <button id="hint1" class="ghost">Get Hint L1</button>
          <button id="hint2" class="ghost">Get Hint L2</button>
          <button id="hint3" class="ghost">Full Solution</button>
          <button id="generateVariations" class="ghost">举一反三</button>
          <button id="needReview" class="ghost">加入复习</button>
          <button id="deleteDetailQuestion" class="danger">删除题目</button>
        </div>
        <article id="analysisBox" class="math-output">${q.ai_hint || q.ai_analysis || "先尝试 Level 1 概念提示；仍卡住再逐级展开到完整解析。"}</article>
        <pre id="variationsBox">${q.ai_variations || "点击“举一反三”，生成同类变式练习。"}</pre>
      </div>
    </div>`;
  dialog.showModal();
  typesetMath($("#detailContent"));

  $("#closeDetail").onclick = () => dialog.close();
  $("#saveDetail").onclick = async () => {
    await updateQuestion(q.id, {
      status: $("#detailStatus").value,
      meta_tags: selectedMetaTags(),
      mistake_reason: selectedMetaTags().join("、"),
      user_note: $("#userNote").value,
      chapter: $("#detailChapter").value,
    });
    dialog.close();
  };
  $("#needReview").onclick = async () => {
    await updateQuestion(q.id, { status: "需复习", meta_tags: selectedMetaTags(), mistake_reason: selectedMetaTags().join("、"), user_note: $("#userNote").value });
    dialog.close();
  };
  $("#deleteDetailQuestion").onclick = async () => {
    dialog.close();
    await deleteQuestion(q.id);
  };
  [1, 2, 3].forEach((level) => {
    $(`#hint${level}`).onclick = async () => {
      $("#analysisBox").textContent = level === 3 ? "正在生成完整 LaTeX 解析..." : "正在生成提示...";
      await api(`/api/questions/${q.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          status: $("#detailStatus").value,
          meta_tags: selectedMetaTags(),
          mistake_reason: selectedMetaTags().join("、"),
          user_note: $("#userNote").value,
          chapter: $("#detailChapter").value,
        }),
      });
      const data = await api(`/api/questions/${q.id}/hint`, { method: "POST", body: JSON.stringify({ level }) });
      $("#analysisBox").textContent = data.hint;
      typesetMath($("#analysisBox"));
      await refresh();
    };
  });
  $("#generateVariations").onclick = async () => {
    $("#variationsBox").textContent = "正在生成难度梯度变式...";
    await api(`/api/questions/${q.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        status: $("#detailStatus").value,
        meta_tags: selectedMetaTags(),
        mistake_reason: selectedMetaTags().join("、"),
        user_note: $("#userNote").value,
        chapter: $("#detailChapter").value,
      }),
    });
    const data = await api(`/api/questions/${q.id}/variations`, { method: "POST", body: "{}" });
    $("#variationsBox").textContent = data.ai_variations;
    typesetMath($("#variationsBox"));
    await refresh();
  };
  setupCropTool(q.id);
}

function setupCropTool(questionId) {
  const stage = $("#cropStage");
  const box = $("#cropBox");
  const save = $("#saveCrop");
  let active = false;
  let start = null;
  let crop = null;

  $("#enableCrop").onclick = () => {
    active = !active;
    box.classList.toggle("hidden", !active);
    save.disabled = !active;
  };

  stage.onpointerdown = (event) => {
    if (!active) return;
    const rect = stage.getBoundingClientRect();
    start = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    crop = { x: start.x, y: start.y, w: 1, h: 1 };
    drawCropBox(crop);
  };

  stage.onpointermove = (event) => {
    if (!active || !start) return;
    const rect = stage.getBoundingClientRect();
    const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
    const y = Math.max(0, Math.min(rect.height, event.clientY - rect.top));
    crop = {
      x: Math.min(start.x, x),
      y: Math.min(start.y, y),
      w: Math.abs(x - start.x),
      h: Math.abs(y - start.y),
    };
    drawCropBox(crop);
  };

  stage.onpointerup = () => {
    start = null;
  };

  save.onclick = async () => {
    if (!crop || crop.w < 20 || crop.h < 20) {
      alert("请拖出一个足够大的裁剪区域。");
      return;
    }
    const rect = stage.getBoundingClientRect();
    const normalized = {
      x: crop.x / rect.width,
      y: crop.y / rect.height,
      w: crop.w / rect.width,
      h: crop.h / rect.height,
    };
    const updated = await api(`/api/questions/${questionId}/crop`, {
      method: "POST",
      body: JSON.stringify({ crop: normalized }),
    });
    $("#detailImage").src = `${updated.image_url}?t=${Date.now()}`;
    box.classList.add("hidden");
    save.disabled = true;
    active = false;
    await refresh();
  };
}

function drawCropBox(crop) {
  const box = $("#cropBox");
  box.style.left = `${crop.x}px`;
  box.style.top = `${crop.y}px`;
  box.style.width = `${crop.w}px`;
  box.style.height = `${crop.h}px`;
}

async function loadChapterStats(documentId) {
  const explicitDoc = documentId ? state.documents.find((doc) => doc.id === documentId) : null;
  if (explicitDoc && documentKind(explicitDoc) === "模拟卷") {
    $("#chapterStatsGrid").innerHTML = "<p>章节统计仅支持做题本，模拟卷请到题库或模拟卷页面查看。</p>";
    return;
  }
  const id =
    documentId ||
    $("#statsDocumentSelect").value ||
    state.documents.find((doc) => documentKind(doc) !== "模拟卷")?.id;
  if (!id) {
    $("#chapterStatsGrid").innerHTML = "<p>还没有做题本。先上传 PDF。</p>";
    return;
  }
  $("#statsDocumentSelect").value = id;
  const data = await api(`/api/documents/${id}/chapter-stats`);
  $("#chapterStatsGrid").innerHTML =
    `<article class="chapter-card radar-card">
      <h3>错因雷达图</h3>
      ${renderRadar(data.meta_tags || [])}
    </article>` +
    data.chapters
      .map((chapter) => {
        const deg = Math.round((chapter.correct_rate / 100) * 360);
        return `
        <article class="chapter-card">
          <h3>${chapter.chapter}</h3>
          <div class="pie" data-label="${chapter.correct_rate}%" style="background: conic-gradient(var(--accent) 0deg ${deg}deg, var(--accent-2) ${deg}deg 360deg)"></div>
          <div class="legend">
            <span>共 ${chapter.total} 题</span>
            <span>做对 ${chapter.correct || 0} · 做错 ${chapter.wrong || 0}</span>
            <span>需复习 ${chapter.review || 0} · 未做 ${chapter.todo || 0}</span>
          </div>
        </article>`;
      })
      .join("") || "<p>这套做题本还没有章节数据。</p>";
  typesetMath($("#chapterStatsGrid"));
}

function renderRadar(items) {
  const size = 260; // 适当放动画布，给文字留出呼吸空间
  const center = size / 2;
  const radius = 80;
  const points = items.map((item, index) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / items.length;
    const value = item.ratio || 0;
    
    // 🌸 动态文字排版算法：根据角度决定向外推的方向
    let anchor = "middle";
    if (Math.cos(angle) < -0.1) anchor = "end";   // 左半边的字靠右对齐（向左推）
    if (Math.cos(angle) > 0.1) anchor = "start";  // 右半边的字靠左对齐（向右推）

    let dy = "0.3em";
    if (Math.sin(angle) < -0.1) dy = "-0.5em"; // 顶部的字往上推
    if (Math.sin(angle) > 0.1) dy = "1em";     // 底部的字往下推

    return {
      ...item,
      x: center + Math.cos(angle) * radius * value,
      y: center + Math.sin(angle) * radius * value,
      ax: center + Math.cos(angle) * radius,
      ay: center + Math.sin(angle) * radius,
      lx: center + Math.cos(angle) * (radius + 15), // 距离顶点的缓冲距离
      ly: center + Math.sin(angle) * (radius + 15),
      anchor, dy
    };
  });
  const polygon = points.map((p) => `${p.x},${p.y}`).join(" ");
  return `
    <svg class="radar" viewBox="0 0 ${size} ${size}" role="img" aria-label="错因雷达图">
      <polygon class="radar-grid" points="${points.map((p) => `${p.ax},${p.ay}`).join(" ")}"></polygon>
      ${points.map((p) => `<line class="radar-axis" x1="${center}" y1="${center}" x2="${p.ax}" y2="${p.ay}"></line>`).join("")}
      <polygon class="radar-area" points="${polygon}"></polygon>
      ${points.map((p) => `<text x="${p.lx}" y="${p.ly}" text-anchor="${p.anchor}" dy="${p.dy}">${p.tag} ${p.count}</text>`).join("")}
    </svg>`;
}

async function loadReflectionPreview() {
  const period = $("#reflectionPeriod").value;
  const data = await api(`/api/reflection?period=${period}`);
  renderReflectionSummary(data);
}

function renderReflectionSummary(data) {
  const total = Number(data.total || 0);
  if (!total) {
    $("#reflectionSummary").innerHTML = '<p class="empty-note">本周期还没有做题记录。先开始做题，再来做周期反思复盘。</p>';
    $("#reflectionSubjectSummary").innerHTML = '<p class="empty-note">导入题目不会计入统计，只有做对、做错、半会或需复习后才会进入这里。</p>';
    $("#reflectionOutput").textContent = "本周期暂无可复盘内容。";
    return;
  }
  $("#reflectionSummary").innerHTML = `
    <div class="summary-pill"><span>周期</span><strong>${data.period === "month" ? "本月" : "本周"}</strong></div>
    <div class="summary-pill"><span>完成/复盘</span><strong>${data.total}</strong></div>
    <div class="summary-pill"><span>做对</span><strong>${data.correct}</strong></div>
    <div class="summary-pill"><span>做错</span><strong>${data.wrong}</strong></div>
    <div class="summary-pill"><span>需复习</span><strong>${data.review}</strong></div>`;
  $("#reflectionSubjectSummary").innerHTML =
    (data.subjects || [])
      .map((item) => {
        const done = item.total || 0;
        const correctRate = done ? Math.round(((item.correct || 0) / done) * 100) : 0;
        return `
        <article class="subject-reflection-card">
          <div>
            <span>科目</span>
            <strong>${item.subject}</strong>
          </div>
          <div class="subject-reflection-grid">
            <span>做题 ${item.total || 0}</span>
            <span>做对 ${item.correct || 0}</span>
            <span>做错 ${item.wrong || 0}</span>
            <span>需复习 ${item.review || 0}</span>
          </div>
          <div class="mini-rate"><span style="width: ${correctRate}%"></span></div>
          <small>正确率 ${correctRate}%</small>
        </article>`;
      })
      .join("") || `<p class="empty-note">本周期还没有已标记的做题记录。导入题目不会计入这里，只有标记做对、做错、半会或需复习后才会统计。</p>`;
}

async function generateReflection() {
  const period = $("#reflectionPeriod").value;
  $("#reflectionOutput").textContent = "正在生成总结与反思...";
  const data = await api("/api/reflection", {
    method: "POST",
    body: JSON.stringify({ period }),
  });
  renderReflectionSummary(data.summary);
  $("#reflectionOutput").textContent = data.reflection;
}

async function loadDaily() {
  const data = await api("/api/daily");
  $("#dailyMessage").textContent = `${data.date} · ${data.message}`;
  $("#dailyGrid").innerHTML =
    (data.groups || [])
      .map(
        (group) => `
        <section class="daily-group">
          <div class="daily-group-head">
            <h3>${group.title}</h3>
            <span>${group.questions.length} 题</span>
          </div>
          <div class="question-grid mini-grid">
            ${group.questions
              .map(
                (q) => `
                <article class="question-card">
                  <div class="thumb" data-open="${q.id}">
                    <img src="${q.image_url}" alt="第 ${q.page_number} 页题目" loading="lazy" />
                  </div>
                  <div class="card-body">
                    <div class="meta">
                      <span>${q.document_title || q.filename || "做题本"} · 第 ${q.page_number} 页</span>
                      <span class="tag status ${statusClass(q.status)}">${q.status}</span>
                    </div>
                    <strong>${q.category}</strong>
                    <span class="tag">${q.chapter || "未识别章节"}</span>
                    <span class="tag kind ${questionKind(q) === "模拟卷" ? "mock" : "paper"}">${questionKind(q)}</span>
                    ${q.daily_kind === "foundation" ? '<span class="tag foundation">前置基础</span>' : ""}
                    ${reviewTag(q)}
                    <div class="actions">
                      <button data-status="做对" data-id="${q.id}">做对</button>
                      <button data-status="做错" data-id="${q.id}">做错</button>
                      <button class="ghost" data-open="${q.id}">详情</button>
                    </div>
                  </div>
                </article>`
              )
              .join("")}
          </div>
        </section>`
      )
      .join("") || "<p>暂无每日练习。先上传做题本或标记错题。</p>";
}

function setView(view) {
  state.view = view;
  document.body.dataset.view = view;
  $$(".view").forEach((node) => node.classList.toggle("active", node.id === view));
  $$(".nav-btn").forEach((node) => node.classList.toggle("active", node.dataset.view === view));
  const titles = {
    dashboard: ["学习总览", "按科目、做题本和知识点追踪练习情况。"],
    documents: ["做题本", "上传和维护章节练习、专项题册等做题本资料。"],
    mockPapers: ["模拟卷", "上传和维护整套试卷，模拟卷与做题本同级管理。"],
    chapterStats: ["章节统计", "用章节正确率看清每套做题本里的薄弱部分。"],
    library: ["总题库", "按做题本、科目、知识点和状态检索题目。"],
    mistakes: ["错题本", "集中处理做错、半会和需要复习的题目。"],
    reflection: ["总结反思", "按周或月复盘重难点、错题和后续规划。"],
    daily: ["每日练习", "优先从薄弱项和最近错题里安排练习。"],
  };
  $("#viewTitle").textContent = titles[view][0];
  $("#viewSubtitle").textContent = titles[view][1];
  if (view === "daily") loadDaily();
  if (view === "chapterStats") loadChapterStats();
  if (view === "reflection") { loadReflectionPreview(); loadReflectionHistory(); }
}

function bindUploadForm(selector, documentKindValue) {
  const formEl = $(selector);
  if (!formEl) return;
  formEl.addEventListener("submit", async (event) => {
    event.preventDefault();
    const fileInput = formEl.querySelector('[name="file"]');
    const status = formEl.querySelector(".upload-status");
    const file = fileInput.files[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("title", formEl.querySelector('[name="title"]').value);
    form.append("subject", formEl.querySelector('[name="subject"]').value);
    form.append("document_kind", documentKindValue);
    form.append("start_page", formEl.querySelector('[name="start_page"]').value);
    form.append("end_page", formEl.querySelector('[name="end_page"]').value);
    status.textContent = `正在导入${documentKindValue}，每页会生成一道题...`;
    try {
      const data = await api("/api/upload", { method: "POST", body: form });
      status.textContent = `已导入「${data.title}」共 ${data.page_count} 道题。`;
      formEl.reset();
      await refresh();
    } catch (error) {
      status.textContent = error.message;
    }
  });
}

bindUploadForm("#bookUploadForm", "做题本");
bindUploadForm("#mockUploadForm", "模拟卷");

$("#documentFilter").addEventListener("change", async (event) => {
  state.documentId = event.target.value;
  const doc = state.documents.find((item) => item.id === state.documentId);
  if (doc) state.subject = doc.subject || state.subject;
  state.category = "";
  state.chapter = "";
  await loadQuestions();
});

$("#dashboardSubjectFilter").addEventListener("change", async (event) => {
  state.dashboardSubject = event.target.value;
  const docs = dashboardDocuments().filter((doc) => !state.dashboardSubject || doc.subject === state.dashboardSubject);
  if (state.dashboardDocumentId && !docs.some((doc) => doc.id === state.dashboardDocumentId)) {
    state.dashboardDocumentId = "";
  }
  await loadDashboardData();
});

$("#dashboardDocumentFilter").addEventListener("change", async (event) => {
  state.dashboardDocumentId = event.target.value;
  await loadDashboardData();
});

$("#subjectFilter").addEventListener("change", async (event) => {
  state.subject = event.target.value;
  const docs = state.documents.filter((doc) => !state.subject || doc.subject === state.subject);
  if (state.documentId && !docs.some((doc) => doc.id === state.documentId)) {
    state.documentId = "";
  }
  state.category = "";
  state.chapter = "";
  await loadQuestions();
});

$("#categoryFilter").addEventListener("change", async (event) => {
  state.category = event.target.value;
  state.chapter = "";
  await loadQuestions();
});

$("#chapterFilter").addEventListener("change", async (event) => {
  state.chapter = event.target.value;
  await loadQuestions();
});

$("#statsDocumentSelect").addEventListener("change", async (event) => {
  await loadChapterStats(event.target.value);
});

$("#reflectionPeriod").addEventListener("change", loadReflectionPreview);
$("#generateReflection").addEventListener("click", generateReflection);

$("#statusFilter").addEventListener("change", async (event) => {
  state.status = event.target.value;
  await loadQuestions();
});

$("#searchInput").addEventListener("input", async (event) => {
  state.search = event.target.value.trim();
  clearTimeout(window.searchTimer);
  window.searchTimer = setTimeout(loadQuestions, 250);
});

$("#focusWrong").addEventListener("click", async () => {
  state.status = "做错";
  setView("library");
  await loadQuestions();
});

$("#focusReview").addEventListener("click", async () => {
  state.status = "需复习";
  setView("library");
  await loadQuestions();
});

$("#showAllQuestions").addEventListener("click", async () => {
  state.documentId = "";
  state.subject = "";
  state.category = "";
  state.chapter = "";
  state.status = "";
  state.search = "";
  $("#searchInput").value = "";
  clearTimeout(window.searchTimer);
  setView("library");
  await loadQuestions();
});

$("#showMockQuestions").addEventListener("click", async () => {
  state.documentId = "";
  state.subject = "";
  state.category = "";
  state.chapter = "";
  state.status = "";
  state.search = "";
  $("#searchInput").value = "";
  clearTimeout(window.searchTimer);
  setView("library");
  await loadQuestions();
  $("#mockQuestionGrid").scrollIntoView({ behavior: "smooth", block: "start" });
});

$("#refreshDaily").addEventListener("click", loadDaily);

document.body.addEventListener("click", async (event) => {
  const nav = event.target.closest(".nav-btn");
  if (nav) setView(nav.dataset.view);

  const open = event.target.closest("[data-open]");
  if (open) openDetail(open.dataset.open);

  const status = event.target.closest("[data-status]");
  if (status) {
    if (status.dataset.status === "做错") {
      await openDetail(status.dataset.id, "做错");
      return;
    }
    await updateQuestion(status.dataset.id, { status: status.dataset.status });
  }

  const deleteQuestionBtn = event.target.closest("[data-delete-question]");
  if (deleteQuestionBtn) {
    await deleteQuestion(deleteQuestionBtn.dataset.deleteQuestion);
  }

  const deleteDocBtn = event.target.closest("[data-delete-doc]");
  if (deleteDocBtn) {
    await deleteDocument(deleteDocBtn.dataset.deleteDoc);
  }

  const editDocBtn = event.target.closest("[data-edit-doc]");
  if (editDocBtn) {
    await editDocument(editDocBtn.dataset.editDoc);
  }

  const viewDocBtn = event.target.closest("[data-view-doc]");
  if (viewDocBtn) {
    state.documentId = viewDocBtn.dataset.viewDoc;
    state.status = "";
    setView("library");
    await loadQuestions();
  }

  const statsDocBtn = event.target.closest("[data-stats-doc]");
  if (statsDocBtn) {
    setView("chapterStats");
    await loadChapterStats(statsDocBtn.dataset.statsDoc);
  }

  const rescanDocBtn = event.target.closest("[data-rescan-doc]");
  if (rescanDocBtn) {
    await rescanDocument(rescanDocBtn.dataset.rescanDoc);
  }
});

loadCountdown();
loadQuote();
refresh();

async function loadCountdown() {
  try {
    const data = await api("/api/countdown");
    const el = document.getElementById("countdownText");
    if (el) el.innerHTML = data.today_formatted + " " + data.weekday + " · 距考研还有 <strong>" + data.days_left + "</strong> 天";
  } catch (e) {
    const el = document.getElementById("countdownText");
    if (el) el.textContent = "加载日期失败";
  }
}

async function loadQuote() {
  try {
    const data = await api("/api/quote");
    const el = document.getElementById("quoteText");
    if (el) el.textContent = data.quote;
  } catch (e) {
    const el = document.getElementById("quoteText");
    if (el) el.textContent = "You are more than what you have become.";
  }
}

async function loadReflectionHistory() {
  try {
    const data = await api("/api/reflections");
    const list = data.reflections || [];
    if (!list.length) {
      $("#historyList").innerHTML = '<p class="empty-note">' + "暂无历史反思记录。" + '</p>';
      return;
    }
    $("#historyList").innerHTML = list.map((ref) => {
      const periodLabel = ref.period === "week" ? "周" : "月";
      const dateLabel = ref.period_start + " ~ " + ref.period_end;
      const preview = (ref.reflection_text || "").slice(0, 120);
      return '<div class="history-item">' +
        '<div class="history-meta">' +
        '<strong>' + periodLabel + '总结</strong>' +
        '<span>' + dateLabel + '</span>' +
        '<small>' + ref.created_at.slice(0, 16) + '</small>' +
        '</div>' +
        '<p class="history-preview">' + preview + (preview.length >= 120 ? "..." : "") + '</p>' +
        '<div class="history-actions">' +
        '<button class="ghost" onclick="downloadReflection(\'' + ref.id + '\')">下载 TXT</button>' +
        '<button class="danger" onclick="deleteReflection(\'' + ref.id + '\')">删除</button>' +
        '</div>' +
        '</div>';
    }).join("");
  } catch (e) {
    $("#historyList").innerHTML = '<p class="empty-note">' + "加载历史失败。" + '</p>';
  }
}
function downloadReflection(refId) {
  const a = document.createElement("a");
  a.href = `/api/reflections/${refId}/download`;
  a.download = "";
  a.click();
}

async function deleteReflection(refId) {
  if (!confirm("确定删除这条历史记录吗？")) return;
  await api(`/api/reflections/${refId}`, { method: "DELETE" });
  await loadReflectionHistory();
}

$("#loadReflectionHistory").addEventListener("click", loadReflectionHistory);
