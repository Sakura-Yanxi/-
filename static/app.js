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

function statusClass(status) {
  if (status === "做错") return "wrong";
  if (status === "需复习" || status === "半会") return "review";
  return "";
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
  renderQuestionGrid("#questionGrid", state.questions);
  renderQuestionGrid("#mistakeGrid", state.questions.filter((q) => ["做错", "需复习", "半会"].includes(q.status)));
}

function renderDocumentFilters() {
  $("#subjectSuggestions").innerHTML = state.subjects.map((subject) => `<option value="${subject}"></option>`).join("");
  $("#statsDocumentSelect").innerHTML = state.documents
    .map((doc) => `<option value="${doc.id}">${doc.title || doc.filename}</option>`)
    .join("");
}

function firstUploadDocuments() {
  const sorted = [...state.documents].sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
  const seen = new Set();
  return sorted.filter((doc) => {
    const key = `${doc.subject}::${doc.title || doc.filename}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function renderDashboardFilters() {
  $("#dashboardSubjectFilter").innerHTML = `<option value="">请选择科目</option>${state.subjects
    .map((subject) => `<option ${subject === state.dashboardSubject ? "selected" : ""}>${subject}</option>`)
    .join("")}`;
  const docs = firstUploadDocuments().filter((doc) => !state.dashboardSubject || doc.subject === state.dashboardSubject);
  $("#dashboardDocumentFilter").innerHTML = `<option value="">请选择做题本</option>${docs
    .map((doc) => `<option value="${doc.id}" ${doc.id === state.dashboardDocumentId ? "selected" : ""}>${doc.title || doc.filename}</option>`)
    .join("")}`;
}

function renderQuestionFilters() {
  const docs = state.documents.filter((doc) => !state.subject || doc.subject === state.subject);
  $("#documentFilter").innerHTML = `<option value="">全部做题本</option>${docs
    .map((doc) => `<option value="${doc.id}" ${doc.id === state.documentId ? "selected" : ""}>${doc.title || doc.filename}</option>`)
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
  const wrong = source.filter((q) => q.status === "做错").length;
  const review = source.filter((q) => ["需复习", "半会"].includes(q.status)).length;
  const weak = [...stats].sort((a, b) => (b.wrong || 0) - (a.wrong || 0))[0];

  $("#totalCount").textContent = total;
  $("#wrongCount").textContent = wrong;
  $("#reviewCount").textContent = review;
  $("#weakCategory").textContent = dashboardReady ? (weak && weak.wrong ? weak.category : "暂无") : "待选择";

  renderStats("#statsList", stats, "category", "选择科目和做题本后会显示对应知识点分布。");
  renderStats("#subjectStatsList", state.dashboardSubjectStats, "subject", "上传 PDF 后会显示科目分布。");
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
  $("#documentGrid").innerHTML =
    state.documents
      .map(
        (doc) => `
        <article class="document-card">
          <div>
            <h3>${doc.title || doc.filename}</h3>
            <p>${doc.subject} · ${doc.question_count || 0} 题 · 错题 ${doc.wrong_count || 0} · 需复习 ${doc.review_count || 0}</p>
            <p>${doc.filename}</p>
          </div>
          <div class="doc-actions">
            <button data-view-doc="${doc.id}">查看</button>
            <button class="ghost" data-stats-doc="${doc.id}">统计</button>
            <button class="ghost" data-rescan-doc="${doc.id}">重扫章节</button>
            <button class="danger" data-delete-doc="${doc.id}">删除</button>
          </div>
        </article>`
      )
      .join("") || "<p>还没有做题本。先从左侧上传 PDF。</p>";
}

function renderQuestionGrid(target, questions) {
  $(target).innerHTML =
    questions
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
            <p class="snippet">${snippet(q.ocr_text)}</p>
            <div class="actions">
              <button data-status="做对" data-id="${q.id}">做对</button>
              <button data-status="做错" data-id="${q.id}">做错</button>
              <button class="danger" data-delete-question="${q.id}">删除</button>
            </div>
          </div>
        </article>`
      )
      .join("") || "<p>还没有题目。先从左侧上传 PDF，或清空筛选条件。</p>";
}

async function updateQuestion(id, payload) {
  await api(`/api/questions/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
  await refresh();
}

async function deleteQuestion(id) {
  if (!confirm("确定删除这道题吗？这个操作会移除题目记录和对应页面图片。")) return;
  await api(`/api/questions/${id}`, { method: "DELETE" });
  await refresh();
}

async function deleteDocument(id) {
  const doc = state.documents.find((item) => item.id === id);
  const name = doc ? doc.title || doc.filename : "这套做题本";
  if (!confirm(`确定删除「${name}」吗？这会删除整套做题本、题目记录和页面图片。`)) return;
  await api(`/api/documents/${id}`, { method: "DELETE" });
  if (state.documentId === id) state.documentId = "";
  await refresh();
}

async function rescanDocument(id) {
  const doc = state.documents.find((item) => item.id === id);
  const name = doc ? doc.title || doc.filename : "这套做题本";
  if (!confirm(`重新扫描「${name}」的页眉/右上角章节吗？这不会调用 AI，也不会消耗 token。`)) return;
  const result = await api(`/api/documents/${id}/rescan-chapters`, { method: "POST", body: "{}" });
  alert(`已重扫 ${result.pages} 页，更新 ${result.updated} 条题目记录。`);
  await refresh();
}

async function openDetail(id) {
  const q = await api(`/api/questions/${id}`);
  const dialog = $("#detailDialog");
  $("#detailContent").innerHTML = `
    <div class="detail">
      <div class="detail-image">
        <img src="${q.image_url}" alt="题目页面" />
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
            ${["未做", "做对", "做错", "半会", "需复习"].map((s) => `<option ${s === q.status ? "selected" : ""}>${s}</option>`).join("")}
          </select>
        </label>
        <label>
          错误原因
          <select id="mistakeReason">
            ${["", "概念不清", "计算错误", "方法不会", "公式记错", "审题错误", "时间不够"].map((s) => `<option ${s === q.mistake_reason ? "selected" : ""}>${s || "未选择"}</option>`).join("")}
          </select>
        </label>
        <label>
          我的备注
          <textarea id="userNote" placeholder="记录这题错在哪里，或者下次要注意什么">${q.user_note || ""}</textarea>
        </label>
        <div class="detail-actions">
          <button id="saveDetail">保存标注</button>
          <button id="analyzeQuestion" class="ghost">生成错题分析</button>
          <button id="generateVariations" class="ghost">举一反三</button>
          <button id="needReview" class="ghost">加入复习</button>
          <button id="deleteDetailQuestion" class="danger">删除题目</button>
        </div>
        <pre id="analysisBox">${q.ai_analysis || "保存错因后，可以生成一份针对这道题的分析。"}</pre>
        <pre id="variationsBox">${q.ai_variations || "点击“举一反三”，生成同类变式练习。"}</pre>
      </div>
    </div>`;
  dialog.showModal();

  $("#closeDetail").onclick = () => dialog.close();
  $("#saveDetail").onclick = async () => {
    await updateQuestion(q.id, {
      status: $("#detailStatus").value,
      mistake_reason: $("#mistakeReason").value,
      user_note: $("#userNote").value,
      chapter: $("#detailChapter").value,
    });
    dialog.close();
  };
  $("#needReview").onclick = async () => {
    await updateQuestion(q.id, { status: "需复习", user_note: $("#userNote").value });
    dialog.close();
  };
  $("#deleteDetailQuestion").onclick = async () => {
    dialog.close();
    await deleteQuestion(q.id);
  };
  $("#analyzeQuestion").onclick = async () => {
    $("#analysisBox").textContent = "正在生成分析...";
    await api(`/api/questions/${q.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        status: $("#detailStatus").value,
        mistake_reason: $("#mistakeReason").value,
        user_note: $("#userNote").value,
        chapter: $("#detailChapter").value,
      }),
    });
    const data = await api(`/api/questions/${q.id}/analyze`, { method: "POST", body: "{}" });
    $("#analysisBox").textContent = data.ai_analysis;
    await refresh();
  };
  $("#generateVariations").onclick = async () => {
    $("#variationsBox").textContent = "正在生成举一反三...";
    await api(`/api/questions/${q.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        status: $("#detailStatus").value,
        mistake_reason: $("#mistakeReason").value,
        user_note: $("#userNote").value,
        chapter: $("#detailChapter").value,
      }),
    });
    const data = await api(`/api/questions/${q.id}/variations`, { method: "POST", body: "{}" });
    $("#variationsBox").textContent = data.ai_variations;
    await refresh();
  };
}

async function loadChapterStats(documentId) {
  const id = documentId || $("#statsDocumentSelect").value || state.documents[0]?.id;
  if (!id) {
    $("#chapterStatsGrid").innerHTML = "<p>还没有做题本。先上传 PDF。</p>";
    return;
  }
  $("#statsDocumentSelect").value = id;
  const data = await api(`/api/documents/${id}/chapter-stats`);
  $("#chapterStatsGrid").innerHTML =
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
}

async function loadReflectionPreview() {
  const period = $("#reflectionPeriod").value;
  const data = await api(`/api/reflection?period=${period}`);
  renderReflectionSummary(data);
}

function renderReflectionSummary(data) {
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
  $$(".view").forEach((node) => node.classList.toggle("active", node.id === view));
  $$(".nav-btn").forEach((node) => node.classList.toggle("active", node.dataset.view === view));
  const titles = {
    dashboard: ["学习总览", "按科目、做题本和知识点追踪练习情况。"],
    documents: ["做题本", "每套 PDF 独立管理，旧资料可以单独删除。"],
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
  if (view === "reflection") loadReflectionPreview();
}

$("#uploadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("#pdfFile").files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  form.append("title", $("#bookTitle").value);
  form.append("subject", $("#subjectInput").value);
  form.append("start_page", $("#startPageInput").value);
  form.append("end_page", $("#endPageInput").value);
  $("#uploadStatus").textContent = "正在导入 PDF，每页会生成一道题...";
  try {
    const data = await api("/api/upload", { method: "POST", body: form });
    $("#uploadStatus").textContent = `已导入「${data.title}」共 ${data.page_count} 道题。`;
    $("#bookTitle").value = "";
    $("#startPageInput").value = "";
    $("#endPageInput").value = "";
    $("#pdfFile").value = "";
    await refresh();
  } catch (error) {
    $("#uploadStatus").textContent = error.message;
  }
});

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
  const docs = firstUploadDocuments().filter((doc) => !state.dashboardSubject || doc.subject === state.dashboardSubject);
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
  setView("library");
  await loadQuestions();
});

$("#refreshDaily").addEventListener("click", loadDaily);

document.body.addEventListener("click", async (event) => {
  const nav = event.target.closest(".nav-btn");
  if (nav) setView(nav.dataset.view);

  const open = event.target.closest("[data-open]");
  if (open) openDetail(open.dataset.open);

  const status = event.target.closest("[data-status]");
  if (status) {
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

refresh();
