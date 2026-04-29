const state = {
  questions: [],
  stats: [],
  categories: [],
  view: "dashboard",
  category: "",
  status: "",
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

async function loadQuestions() {
  const params = new URLSearchParams();
  if (state.category) params.set("category", state.category);
  if (state.status) params.set("status", state.status);
  if (state.search) params.set("search", state.search);
  const data = await api(`/api/questions?${params}`);
  state.questions = data.questions;
  state.stats = data.stats;
  state.categories = data.categories;
  renderAll();
}

function renderAll() {
  renderFilters();
  renderDashboard();
  renderQuestionGrid("#questionGrid", state.questions);
  renderQuestionGrid("#mistakeGrid", state.questions.filter((q) => ["做错", "需复习", "半会"].includes(q.status)));
}

function renderFilters() {
  const select = $("#categoryFilter");
  const current = select.value || state.category;
  select.innerHTML = `<option value="">全部知识点</option>${state.categories
    .map((category) => `<option ${category === current ? "selected" : ""}>${category}</option>`)
    .join("")}`;
  $("#statusFilter").value = state.status;
}

function renderDashboard() {
  const total = state.questions.length;
  const wrong = state.questions.filter((q) => q.status === "做错").length;
  const review = state.questions.filter((q) => ["需复习", "半会"].includes(q.status)).length;
  const weak = [...state.stats].sort((a, b) => (b.wrong || 0) - (a.wrong || 0))[0];

  $("#totalCount").textContent = total;
  $("#wrongCount").textContent = wrong;
  $("#reviewCount").textContent = review;
  $("#weakCategory").textContent = weak && weak.wrong ? weak.category : "暂无";

  const max = Math.max(...state.stats.map((item) => item.total), 1);
  $("#statsList").innerHTML =
    state.stats
      .map(
        (item) => `
        <div class="stat-row">
          <strong>${item.category}</strong>
          <div class="bar"><span style="width: ${(item.total / max) * 100}%"></span></div>
          <span>${item.total} 题</span>
        </div>`
      )
      .join("") || "<p>上传 PDF 后会显示知识点分布。</p>";
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
              <span>${q.filename || "做题本"} · 第 ${q.page_number} 页</span>
              <span class="tag status ${statusClass(q.status)}">${q.status}</span>
            </div>
            <strong>${q.category}</strong>
            <span class="tag">${q.subcategory || q.difficulty}</span>
            <p class="snippet">${snippet(q.ocr_text)}</p>
            <div class="actions">
              <button data-status="做对" data-id="${q.id}">做对</button>
              <button data-status="做错" data-id="${q.id}">做错</button>
              <button class="ghost" data-open="${q.id}">详情</button>
            </div>
          </div>
        </article>`
      )
      .join("") || "<p>还没有题目。先从左侧上传 PDF。</p>";
}

async function updateQuestion(id, payload) {
  await api(`/api/questions/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
  await loadQuestions();
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
            <p>${q.filename} · 第 ${q.page_number} 页 · ${q.difficulty}</p>
          </div>
          <button class="ghost" id="closeDetail">关闭</button>
        </div>
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
          <button id="needReview" class="ghost">加入复习</button>
        </div>
        <pre id="analysisBox">${q.ai_analysis || "保存错因后，可以生成一份针对这道题的分析。"}</pre>
      </div>
    </div>`;
  dialog.showModal();

  $("#closeDetail").onclick = () => dialog.close();
  $("#saveDetail").onclick = async () => {
    await updateQuestion(q.id, {
      status: $("#detailStatus").value,
      mistake_reason: $("#mistakeReason").value,
      user_note: $("#userNote").value,
    });
    dialog.close();
  };
  $("#needReview").onclick = async () => {
    await updateQuestion(q.id, { status: "需复习", user_note: $("#userNote").value });
    dialog.close();
  };
  $("#analyzeQuestion").onclick = async () => {
    $("#analysisBox").textContent = "正在生成分析...";
    await api(`/api/questions/${q.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        status: $("#detailStatus").value,
        mistake_reason: $("#mistakeReason").value,
        user_note: $("#userNote").value,
      }),
    });
    const data = await api(`/api/questions/${q.id}/analyze`, { method: "POST", body: "{}" });
    $("#analysisBox").textContent = data.ai_analysis;
    await loadQuestions();
  };
}

async function loadDaily() {
  const data = await api("/api/daily");
  $("#dailyMessage").textContent = `${data.date} · ${data.message}`;
  renderQuestionGrid("#dailyGrid", data.plan);
}

function setView(view) {
  state.view = view;
  $$(".view").forEach((node) => node.classList.toggle("active", node.id === view));
  $$(".nav-btn").forEach((node) => node.classList.toggle("active", node.dataset.view === view));
  const titles = {
    dashboard: ["学习总览", "把 PDF 做题本拆成题库，再围绕错题安排复习。"],
    library: ["题库", "按知识点、状态和文字检索题目。"],
    mistakes: ["错题本", "集中处理做错、半会和需要复习的题目。"],
    daily: ["每日练习", "优先从薄弱项和最近错题里安排练习。"],
  };
  $("#viewTitle").textContent = titles[view][0];
  $("#viewSubtitle").textContent = titles[view][1];
  if (view === "daily") loadDaily();
}

$("#uploadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("#pdfFile").files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  $("#uploadStatus").textContent = "正在导入 PDF，每页会生成一道题...";
  try {
    const data = await api("/api/upload", { method: "POST", body: form });
    $("#uploadStatus").textContent = `已导入 ${data.page_count} 道题。`;
    await loadQuestions();
  } catch (error) {
    $("#uploadStatus").textContent = error.message;
  }
});

$("#categoryFilter").addEventListener("change", async (event) => {
  state.category = event.target.value;
  await loadQuestions();
});

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
});

loadQuestions();
