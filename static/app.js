let envsData = {};
let editingEnvName = "";
let casesList = [];
let currentCase = null; // { filename, name, description, steps }

let activeRespTab = "body";
let toastTimer = null;
let apiStepTabMap = {}; // stepIdx -> 'body' | 'headers' | 'params' | 'extract' | 'assert'
let stepCollapseMap = {}; // stepIdx -> boolean
let caseDirty = false;
let envDirty = false;
let dbgBodyType = "json";
let dbgFormFields = [];
let activeReportKind = "allure";
let latestReportStatus = null;
let caseRunResultsMap = {}; // filename -> case_record
let curlModalMode = "debug"; // 'debug' | 'case'
let stepResultSubTabMap = {}; // stepIdx -> 'resp' | 'req' | 'headers'
const MAX_UNDO_HISTORY = 50;
let caseUndoStack = [];
let caseRedoStack = [];
let caseCurrentSnapshot = "";
let caseSavedSnapshot = "";
let isRestoringCase = false;
let caseCommitTimer = null;
let envUndoStack = [];
let envRedoStack = [];
let envCurrentSnapshot = "";
let envSavedSnapshot = "";
let isRestoringEnv = false;
let envCommitTimer = null;
let isTestRunning = false;

const UI_ACTION_GROUPS = [
  {
    group: "页面导航",
    items: [
      { value: "open", label: "打开网页 (open)" },
      { value: "refresh", label: "刷新页面 (refresh)" },
      { value: "back", label: "后退一页 (back)" },
      { value: "forward", label: "前进一页 (forward)" },
    ],
  },
  {
    group: "鼠标与输入",
    items: [
      { value: "click", label: "点击元素 (click)" },
      { value: "double_click", label: "双击元素 (double_click)" },
      { value: "right_click", label: "右键元素 (right_click)" },
      { value: "hover", label: "鼠标悬停 (hover)" },
      { value: "input", label: "输入文本 (input)" },
      { value: "clear", label: "清空输入框 (clear)" },
      { value: "press_key", label: "按键操作 (press_key)" },
      { value: "select_option", label: "下拉框选择 (select_option)" },
      { value: "upload_file", label: "上传文件 (upload_file)" },
      { value: "scroll_to", label: "页面/元素滚动 (scroll_to)" },
    ],
  },
  {
    group: "等待与窗口/框架",
    items: [
      { value: "wait", label: "等待秒数 (wait)" },
      { value: "wait_element", label: "等待元素可见 (wait_element)" },
      { value: "switch_tab", label: "切换标签页 (switch_tab)" },
      { value: "close_tab", label: "关闭当前标签页 (close_tab)" },
      { value: "switch_iframe", label: "切换 iframe (switch_iframe)" },
      { value: "handle_alert", label: "处理弹窗 (handle_alert)" },
    ],
  },
  {
    group: "断言校验",
    items: [
      { value: "assert_text", label: "断言页面文本 (assert_text)" },
      { value: "assert_title", label: "断言网页标题 (assert_title)" },
      { value: "assert_url", label: "断言当前网址 (assert_url)" },
      { value: "assert_element", label: "断言元素可见 (assert_element)" },
      { value: "assert_element_text", label: "断言元素文本 (assert_element_text)" },
      { value: "assert_element_hidden", label: "断言元素隐藏/消失 (assert_element_hidden)" },
    ],
  },
  {
    group: "数据与高级",
    items: [
      { value: "get_text", label: "提取元素文本到变量 (get_text)" },
      { value: "set_local_storage", label: "写入 LocalStorage (set_local_storage)" },
      { value: "set_cookie", label: "写入 Cookie (set_cookie)" },
      { value: "execute_js", label: "执行 JS 脚本 (execute_js)" },
      { value: "screenshot", label: "截图保存 (screenshot)" },
    ],
  },
];

const LOCATOR_TYPES = [
  { value: "css", label: "CSS 选择器" },
  { value: "xpath", label: "XPath" },
  { value: "id", label: "ID" },
  { value: "name", label: "Name" },
  { value: "text", label: "文本包含 (Text)" },
  { value: "placeholder", label: "Placeholder 占位符" },
];

const ASSERT_TYPES = [
  { value: "status_code", label: "状态码等于" },
  { value: "json_equals", label: "JSON 字段等于" },
  { value: "json_not_equals", label: "JSON 字段不等于" },
  { value: "json_contains", label: "JSON 字段包含" },
  { value: "json_exists", label: "JSON 字段存在非空" },
  { value: "json_gt", label: "JSON 数值大于" },
  { value: "json_lt", label: "JSON 数值小于" },
  { value: "body_contains", label: "响应文本包含" },
  { value: "header_contains", label: "响应头包含" },
  { value: "response_time_lt", label: "响应耗时小于(ms)" },
  { value: "regex_match", label: "响应体正则匹配" },
];

function showToast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 2600);
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function safeParseJson(text, fallback) {
  const trimmed = (text || "").trim();
  if (!trimmed) return fallback;
  return JSON.parse(trimmed);
}

function setCaseDirty(dirty) {
  caseDirty = Boolean(dirty);
  const btn = document.getElementById("save-case-btn");
  if (btn) {
    btn.textContent = caseDirty ? "保存 ●" : "保存";
    btn.classList.toggle("btn-dirty", caseDirty);
  }
}

function setEnvDirty(dirty) {
  envDirty = Boolean(dirty);
  const btn = document.getElementById("save-envs-btn");
  if (btn) {
    btn.textContent = envDirty ? "保存配置 ●" : "保存配置";
    btn.classList.toggle("btn-dirty", envDirty);
  }
}

function captureCaseSnapshot() {
  if (!currentCase) return "";
  const nameEl = document.getElementById("case-name");
  const descEl = document.getElementById("case-desc");
  return JSON.stringify({
    name: nameEl ? nameEl.value : (currentCase.name || ""),
    description: descEl ? descEl.value : (currentCase.description || ""),
    steps: currentCase.steps || [],
  });
}

function updateCaseHistoryButtons(curSnap = null) {
  const undoBtn = document.getElementById("case-undo-btn");
  const redoBtn = document.getElementById("case-redo-btn");
  const cur = curSnap !== null ? curSnap : (currentCase ? captureCaseSnapshot() : "");
  const hasPending = Boolean(cur && caseCurrentSnapshot && cur !== caseCurrentSnapshot);
  const hasUndo = Boolean(
    cur && (hasPending || (caseUndoStack.length > 0 && (caseUndoStack.length > 1 || caseUndoStack[0] !== cur)))
  );
  const hasRedo = Boolean(
    cur && !hasPending && caseRedoStack.length > 0 && (caseRedoStack.length > 1 || caseRedoStack[0] !== cur)
  );
  if (undoBtn) undoBtn.disabled = !hasUndo;
  if (redoBtn) redoBtn.disabled = !hasRedo;
}

function resetCaseHistory() {
  clearTimeout(caseCommitTimer);
  caseUndoStack = [];
  caseRedoStack = [];
  caseCurrentSnapshot = captureCaseSnapshot();
  caseSavedSnapshot = caseCurrentSnapshot;
  updateCaseHistoryButtons();
}

function recordCaseChange() {
  if (!currentCase || isRestoringCase) return;
  clearTimeout(caseCommitTimer);
  const next = captureCaseSnapshot();
  if (!next || next === caseCurrentSnapshot) {
    setCaseDirty(Boolean(next && next !== caseSavedSnapshot));
    updateCaseHistoryButtons(next);
    return;
  }
  if (caseCurrentSnapshot) {
    caseUndoStack.push(caseCurrentSnapshot);
    if (caseUndoStack.length > MAX_UNDO_HISTORY) caseUndoStack.shift();
  }
  caseCurrentSnapshot = next;
  caseRedoStack = [];
  setCaseDirty(next !== caseSavedSnapshot);
  updateCaseHistoryButtons(next);
}

function scheduleCaseCommit() {
  if (!currentCase || isRestoringCase) return;
  const cur = captureCaseSnapshot();
  setCaseDirty(Boolean(cur && cur !== caseSavedSnapshot));
  clearTimeout(caseCommitTimer);
  caseCommitTimer = setTimeout(() => recordCaseChange(), 300);
  updateCaseHistoryButtons(cur);
}

function applyCaseSnapshot(snap) {
  if (!currentCase || !snap) return;
  isRestoringCase = true;
  try {
    if (document.activeElement && typeof document.activeElement.blur === "function" && document.activeElement !== document.body) {
      document.activeElement.blur();
    }
    const data = JSON.parse(snap);
    currentCase.name = data.name || "";
    currentCase.description = data.description || "";
    currentCase.steps = Array.isArray(data.steps) ? data.steps : [];
    const nameEl = document.getElementById("case-name");
    const descEl = document.getElementById("case-desc");
    if (nameEl) nameEl.value = currentCase.name;
    if (descEl) descEl.value = currentCase.description;
    renderSteps();
    setCaseDirty(snap !== caseSavedSnapshot);
  } finally {
    isRestoringCase = false;
  }
}

function undoCase() {
  if (!currentCase) return;
  clearTimeout(caseCommitTimer);
  const cur = captureCaseSnapshot();
  if (cur && caseCurrentSnapshot && cur !== caseCurrentSnapshot) {
    caseRedoStack.push(cur);
    if (caseRedoStack.length > MAX_UNDO_HISTORY) caseRedoStack.shift();
    applyCaseSnapshot(caseCurrentSnapshot);
    updateCaseHistoryButtons();
    showToast("已撤销用例修改");
    return;
  }
  while (caseUndoStack.length && caseUndoStack[caseUndoStack.length - 1] === caseCurrentSnapshot) {
    caseUndoStack.pop();
  }
  if (!caseUndoStack.length) {
    updateCaseHistoryButtons();
    return;
  }
  if (caseCurrentSnapshot) {
    caseRedoStack.push(caseCurrentSnapshot);
    if (caseRedoStack.length > MAX_UNDO_HISTORY) caseRedoStack.shift();
  }
  const prev = caseUndoStack.pop();
  caseCurrentSnapshot = prev;
  applyCaseSnapshot(prev);
  updateCaseHistoryButtons();
  showToast("已撤销用例修改");
}

function redoCase() {
  if (!currentCase) return;
  clearTimeout(caseCommitTimer);
  const cur = captureCaseSnapshot();
  if (cur && caseCurrentSnapshot && cur !== caseCurrentSnapshot) {
    updateCaseHistoryButtons();
    return;
  }
  while (caseRedoStack.length && caseRedoStack[caseRedoStack.length - 1] === caseCurrentSnapshot) {
    caseRedoStack.pop();
  }
  if (!caseRedoStack.length) {
    updateCaseHistoryButtons();
    return;
  }
  if (caseCurrentSnapshot) {
    caseUndoStack.push(caseCurrentSnapshot);
    if (caseUndoStack.length > MAX_UNDO_HISTORY) caseUndoStack.shift();
  }
  const next = caseRedoStack.pop();
  caseCurrentSnapshot = next;
  applyCaseSnapshot(next);
  updateCaseHistoryButtons();
  showToast("已重做用例修改");
}

function getEnvTableRows() {
  const rows = [];
  document.querySelectorAll("#env-vars-tbody tr").forEach((tr) => {
    const k = tr.querySelector(".env-key")?.value ?? "";
    const v = tr.querySelector(".env-val")?.value ?? "";
    rows.push([k, v]);
  });
  return rows;
}

function captureEnvSnapshot() {
  syncEditingEnvFromTable();
  return JSON.stringify({
    envsData,
    editingEnvName,
    editingRows: getEnvTableRows(),
  });
}

function updateEnvHistoryButtons(curSnap = null) {
  const undoBtn = document.getElementById("env-undo-btn");
  const redoBtn = document.getElementById("env-redo-btn");
  const cur = curSnap !== null ? curSnap : captureEnvSnapshot();
  const hasPending = Boolean(envCurrentSnapshot && cur !== envCurrentSnapshot);
  const hasUndo = hasPending || (envUndoStack.length > 0 && (envUndoStack.length > 1 || envUndoStack[0] !== cur));
  const hasRedo = !hasPending && envRedoStack.length > 0 && (envRedoStack.length > 1 || envRedoStack[0] !== cur);
  if (undoBtn) undoBtn.disabled = !hasUndo;
  if (redoBtn) redoBtn.disabled = !hasRedo;
}

function resetEnvHistory() {
  clearTimeout(envCommitTimer);
  envUndoStack = [];
  envRedoStack = [];
  envCurrentSnapshot = captureEnvSnapshot();
  envSavedSnapshot = envCurrentSnapshot;
  updateEnvHistoryButtons();
}

function recordEnvChange() {
  if (isRestoringEnv) return;
  clearTimeout(envCommitTimer);
  const next = captureEnvSnapshot();
  if (!next || next === envCurrentSnapshot) {
    setEnvDirty(Boolean(next && next !== envSavedSnapshot));
    updateEnvHistoryButtons(next);
    return;
  }
  if (envCurrentSnapshot) {
    envUndoStack.push(envCurrentSnapshot);
    if (envUndoStack.length > MAX_UNDO_HISTORY) envUndoStack.shift();
  }
  envCurrentSnapshot = next;
  envRedoStack = [];
  setEnvDirty(next !== envSavedSnapshot);
  updateEnvHistoryButtons(next);
}

function scheduleEnvCommit() {
  if (isRestoringEnv) return;
  const cur = captureEnvSnapshot();
  setEnvDirty(Boolean(cur && cur !== envSavedSnapshot));
  clearTimeout(envCommitTimer);
  envCommitTimer = setTimeout(() => recordEnvChange(), 300);
  updateEnvHistoryButtons(cur);
}

function applyEnvSnapshot(snap) {
  if (!snap) return;
  isRestoringEnv = true;
  try {
    if (document.activeElement && typeof document.activeElement.blur === "function" && document.activeElement !== document.body) {
      document.activeElement.blur();
    }
    const data = JSON.parse(snap);
    envsData = data.envsData || {};
    editingEnvName = data.editingEnvName || Object.keys(envsData)[0] || "";
    renderGlobalEnvSelect();
    renderEnvEditor();
    if (Array.isArray(data.editingRows)) {
      const tbody = document.getElementById("env-vars-tbody");
      if (tbody) {
        tbody.innerHTML = data.editingRows.map(([k, v]) => envRowHtml(k, v)).join("");
      }
    }
    setEnvDirty(snap !== envSavedSnapshot);
  } finally {
    isRestoringEnv = false;
  }
}

function undoEnv() {
  clearTimeout(envCommitTimer);
  const cur = captureEnvSnapshot();
  if (cur && envCurrentSnapshot && cur !== envCurrentSnapshot) {
    envRedoStack.push(cur);
    if (envRedoStack.length > MAX_UNDO_HISTORY) envRedoStack.shift();
    applyEnvSnapshot(envCurrentSnapshot);
    updateEnvHistoryButtons();
    showToast("已撤销环境变量修改");
    return;
  }
  while (envUndoStack.length && envUndoStack[envUndoStack.length - 1] === envCurrentSnapshot) {
    envUndoStack.pop();
  }
  if (!envUndoStack.length) {
    updateEnvHistoryButtons();
    return;
  }
  if (envCurrentSnapshot) {
    envRedoStack.push(envCurrentSnapshot);
    if (envRedoStack.length > MAX_UNDO_HISTORY) envRedoStack.shift();
  }
  const prev = envUndoStack.pop();
  envCurrentSnapshot = prev;
  applyEnvSnapshot(prev);
  updateEnvHistoryButtons();
  showToast("已撤销环境变量修改");
}

function redoEnv() {
  clearTimeout(envCommitTimer);
  const cur = captureEnvSnapshot();
  if (cur && envCurrentSnapshot && cur !== envCurrentSnapshot) {
    updateEnvHistoryButtons();
    return;
  }
  while (envRedoStack.length && envRedoStack[envRedoStack.length - 1] === envCurrentSnapshot) {
    envRedoStack.pop();
  }
  if (!envRedoStack.length) {
    updateEnvHistoryButtons();
    return;
  }
  if (envCurrentSnapshot) {
    envUndoStack.push(envCurrentSnapshot);
    if (envUndoStack.length > MAX_UNDO_HISTORY) envUndoStack.shift();
  }
  const next = envRedoStack.pop();
  envCurrentSnapshot = next;
  applyEnvSnapshot(next);
  updateEnvHistoryButtons();
  showToast("已重做环境变量修改");
}

function removeEnvVarRow(btn) {
  btn.closest("tr")?.remove();
  recordEnvChange();
}

function openShortcutsModal() {
  document.getElementById("shortcuts-modal")?.classList.remove("hidden");
}

function closeShortcutsModal() {
  document.getElementById("shortcuts-modal")?.classList.add("hidden");
}

function isTextInputFocused() {
  const el = document.activeElement;
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
}

function hasOpenModal() {
  return Boolean(document.querySelector(".modal:not(.hidden)"));
}

function switchTab(tabName) {
  document.querySelectorAll(".nav-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-panel").forEach((p) => {
    p.classList.toggle("active", p.id === `tab-${tabName}`);
  });
}

function switchDebugSubTab(name, btn) {
  document.querySelectorAll("#tab-debug .sub-tab").forEach((b) => b.classList.remove("active"));
  document.querySelectorAll("#tab-debug .sub-panel").forEach((p) => p.classList.remove("active"));
  btn.classList.add("active");
  document.getElementById(`dbg-sub-${name}`).classList.add("active");
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `请求失败 (${res.status})`);
  }
  return data;
}

// ---------- 环境管理 ----------
async function loadEnvs() {
  const data = await apiFetch("/api/envs");
  envsData = data.environments || {};
  const names = Object.keys(envsData);
  if (!names.length) {
    envsData = { local_demo: { base_url: "http://127.0.0.1:8000" } };
  }
  renderGlobalEnvSelect();
  if (!editingEnvName || !envsData[editingEnvName]) {
    editingEnvName = Object.keys(envsData)[0];
  }
  renderEnvEditor();
  setEnvDirty(false);
  resetEnvHistory();
}

function renderGlobalEnvSelect() {
  const sel = document.getElementById("global-env-select");
  const prev = sel.value;
  sel.innerHTML = Object.keys(envsData)
    .map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`)
    .join("");
  const prefs = loadPrefs();
  if (prefs.env && envsData[prefs.env]) sel.value = prefs.env;
  else if (prev && envsData[prev]) sel.value = prev;
}

function renderEnvEditor() {
  const listEl = document.getElementById("env-list");
  listEl.innerHTML = Object.keys(envsData)
    .map(
      (n) => `<div class="env-item ${n === editingEnvName ? "active" : ""}" onclick="selectEditingEnv('${escapeHtml(n)}')">${escapeHtml(n)}</div>`
    )
    .join("");

  document.getElementById("editing-env-title").textContent = `环境：${editingEnvName}`;
  const vars = envsData[editingEnvName] || {};
  const tbody = document.getElementById("env-vars-tbody");
  tbody.innerHTML = Object.entries(vars)
    .map(([k, v]) => envRowHtml(k, v))
    .join("");
}

function envRowHtml(k = "", v = "") {
  return `<tr>
    <td><input class="env-key" value="${escapeHtml(k)}" placeholder="变量名" oninput="scheduleEnvCommit()" onchange="recordEnvChange()" /></td>
    <td><input class="env-val" value="${escapeHtml(v)}" placeholder="变量值" oninput="scheduleEnvCommit()" onchange="recordEnvChange()" /></td>
    <td><button class="btn btn-sm btn-danger-outline" onclick="removeEnvVarRow(this)">删除</button></td>
  </tr>`;
}

function selectEditingEnv(name) {
  recordEnvChange();
  syncEditingEnvFromTable();
  editingEnvName = name;
  renderEnvEditor();
  envCurrentSnapshot = captureEnvSnapshot();
  updateEnvHistoryButtons();
}

function syncEditingEnvFromTable() {
  if (!editingEnvName) return;
  const obj = {};
  document.querySelectorAll("#env-vars-tbody tr").forEach((tr) => {
    const k = tr.querySelector(".env-key").value.trim();
    const v = tr.querySelector(".env-val").value;
    if (k) obj[k] = v;
  });
  envsData[editingEnvName] = obj;
}

function addEnvVarRow() {
  document.getElementById("env-vars-tbody").insertAdjacentHTML("beforeend", envRowHtml());
  recordEnvChange();
}

function addEnvironment() {
  const name = prompt("请输入新环境名称（如 test / prod）：");
  if (!name || !name.trim()) return;
  const trimmed = name.trim();
  syncEditingEnvFromTable();
  if (!envsData[trimmed]) {
    envsData[trimmed] = { base_url: "http://127.0.0.1:8000" };
  }
  editingEnvName = trimmed;
  renderGlobalEnvSelect();
  renderEnvEditor();
  recordEnvChange();
}

async function saveEnvs() {
  try {
    clearTimeout(envCommitTimer);
    syncEditingEnvFromTable();
    await apiFetch("/api/envs", {
      method: "PUT",
      body: JSON.stringify({ environments: envsData }),
    });
    renderGlobalEnvSelect();
    envSavedSnapshot = captureEnvSnapshot();
    envCurrentSnapshot = envSavedSnapshot;
    setEnvDirty(false);
    updateEnvHistoryButtons(envCurrentSnapshot);
    showToast("环境配置已保存");
  } catch (err) {
    showToast("保存环境配置失败: " + err.message);
  }
}

async function deleteCurrentEnvironment() {
  const names = Object.keys(envsData);
  if (names.length <= 1) {
    showToast("至少保留一个环境配置");
    return;
  }
  if (!confirm(`确定删除环境「${editingEnvName}」吗？`)) return;
  try {
    delete envsData[editingEnvName];
    editingEnvName = Object.keys(envsData)[0];
    await apiFetch("/api/envs", {
      method: "PUT",
      body: JSON.stringify({ environments: envsData }),
    });
    renderGlobalEnvSelect();
    renderEnvEditor();
    recordEnvChange();
    showToast("已删除环境");
  } catch (err) {
    showToast("删除环境失败: " + err.message);
  }
}

const _NOISE_HEADERS = new Set([
  "host",
  "content-length",
  "connection",
  "accept-encoding",
  "pragma",
  "cache-control",
  "origin",
  "referer",
  "user-agent",
  "sec-fetch-dest",
  "sec-fetch-mode",
  "sec-fetch-site",
  "sec-ch-ua",
  "sec-ch-ua-mobile",
  "sec-ch-ua-platform",
]);

function openCurlModal(mode = "debug") {
  curlModalMode = mode;
  document.getElementById("curl-input").value = "";
  document.getElementById("curl-modal").classList.remove("hidden");
}

function closeCurlModal() {
  document.getElementById("curl-modal").classList.add("hidden");
}

function parseCurlCommand(raw) {
  const cleaned = raw.replace(/\\\r?\n/g, " ").trim();
  const tokens = [];
  let cur = "";
  let quote = null;
  for (let i = 0; i < cleaned.length; i++) {
    const ch = cleaned[i];
    if (quote) {
      if (ch === "\\" && i + 1 < cleaned.length && quote === '"') {
        cur += cleaned[++i];
      } else if (ch === quote) {
        quote = null;
      } else {
        cur += ch;
      }
    } else if (ch === "'" || ch === '"') {
      quote = ch;
    } else if (/\s/.test(ch)) {
      if (cur) {
        tokens.push(cur);
        cur = "";
      }
    } else {
      cur += ch;
    }
  }
  if (cur) tokens.push(cur);

  let method = "";
  let url = "";
  const headers = {};
  const params = {};
  let body = "";
  let bodyType = "json";
  const formFields = [];

  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t === "curl") continue;
    if ((t === "-X" || t === "--request") && i + 1 < tokens.length) {
      method = tokens[++i].toUpperCase();
    } else if ((t === "-H" || t === "--header") && i + 1 < tokens.length) {
      const h = tokens[++i];
      const idx = h.indexOf(":");
      if (idx > 0) {
        const hk = h.slice(0, idx).trim();
        const hv = h.slice(idx + 1).trim();
        if (!_NOISE_HEADERS.has(hk.toLowerCase()) && !(hk.toLowerCase() === "content-type" && hv.includes("multipart/form-data"))) {
          headers[hk] = hv;
        }
      }
    } else if ((t === "-b" || t === "--cookie") && i + 1 < tokens.length) {
      headers["Cookie"] = tokens[++i];
    } else if ((t === "-F" || t === "--form") && i + 1 < tokens.length) {
      const f = tokens[++i];
      const eq = f.indexOf("=");
      if (eq > 0) {
        const fk = f.slice(0, eq).trim();
        const fv = f.slice(eq + 1).trim();
        if (fv.startsWith("@")) {
          formFields.push({ key: fk, value: fv.slice(1), type: "file" });
        } else {
          formFields.push({ key: fk, value: fv, type: "text" });
        }
        bodyType = "form_data";
        if (!method) method = "POST";
      }
    } else if (t === "--data-urlencode" && i + 1 < tokens.length) {
      const f = tokens[++i];
      const eq = f.indexOf("=");
      if (eq > 0) {
        formFields.push({ key: f.slice(0, eq), value: f.slice(eq + 1), type: "text" });
      }
      bodyType = "form_urlencoded";
      if (!method) method = "POST";
    } else if ((t === "-d" || t === "--data" || t === "--data-raw" || t === "--data-binary") && i + 1 < tokens.length) {
      body = tokens[++i];
      if (!method) method = "POST";
    } else if (!t.startsWith("-") && /^https?:\/\//i.test(t)) {
      url = t;
    }
  }

  if (url && url.includes("?")) {
    try {
      const u = new URL(url);
      u.searchParams.forEach((v, k) => {
        params[k] = v;
      });
      url = `${u.origin}${u.pathname}`;
    } catch {
      // keep raw url
    }
  }
  return { method: method || "GET", url, headers, params, body, bodyType, formFields };
}

function confirmImportCurl() {
  const raw = document.getElementById("curl-input").value.trim();
  if (!raw) {
    showToast("请先粘贴 cURL 命令");
    return;
  }
  const parsed = parseCurlCommand(raw);
  if (!parsed.url) {
    showToast("未能识别到 URL，请检查 cURL 格式");
    return;
  }

  if (curlModalMode === "case" && currentCase) {
    const reqObj = {
      method: parsed.method,
      url: parsed.url,
      headers: parsed.headers,
      params: parsed.params,
    };
    if (parsed.bodyType === "form_data" || parsed.bodyType === "form_urlencoded") {
      reqObj.body_type = parsed.bodyType;
      reqObj.form_fields = parsed.formFields;
    } else if (parsed.body) {
      try {
        reqObj.json = JSON.parse(parsed.body);
      } catch {
        reqObj.body_type = "raw";
        reqObj.body = parsed.body;
      }
    }
    currentCase.steps.push({
      type: "api",
      name: `${parsed.method} ${parsed.url.split("/").pop() || "cURL接口"}`,
      request: reqObj,
      extract: [],
      assertions: [{ type: "status_code", target: "", expected: 200 }],
    });
    setCaseDirty(true);
    closeCurlModal();
    renderSteps();
    recordCaseChange();
    showToast("已从 cURL 添加新步骤（已自动过滤浏览器冗余头）");
    return;
  }

  document.getElementById("dbg-method").value = parsed.method;
  document.getElementById("dbg-url").value = parsed.url;
  document.getElementById("dbg-headers").value = JSON.stringify(parsed.headers, null, 2);
  document.getElementById("dbg-params").value = JSON.stringify(parsed.params, null, 2);
  if (parsed.bodyType === "form_data" || parsed.bodyType === "form_urlencoded") {
    dbgFormFields = parsed.formFields;
    switchDebugBodyType(parsed.bodyType);
    document.getElementById("dbg-body").value = "";
  } else {
    switchDebugBodyType("json");
    if (parsed.body) {
      try {
        document.getElementById("dbg-body").value = JSON.stringify(JSON.parse(parsed.body), null, 2);
      } catch {
        switchDebugBodyType("raw");
        document.getElementById("dbg-body").value = parsed.body;
      }
    } else {
      document.getElementById("dbg-body").value = "";
    }
  }
  closeCurlModal();
  showToast("cURL 已解析并填入（已自动过滤冗余请求头）");
}

// ---------- 接口调试 ----------
function switchDebugBodyType(type) {
  dbgBodyType = type || "json";
  document.querySelectorAll('input[name="dbg-body-type"]').forEach((r) => {
    r.checked = r.value === dbgBodyType;
  });
  const isForm = dbgBodyType === "form_urlencoded" || dbgBodyType === "form_data";
  document.getElementById("dbg-body-text-wrap").classList.toggle("hidden", isForm);
  document.getElementById("dbg-body-form-wrap").classList.toggle("hidden", !isForm);
  document.getElementById("dbg-form-type-th").classList.toggle("hidden", dbgBodyType !== "form_data");
  if (isForm && !dbgFormFields.length) {
    dbgFormFields.push({ key: "", value: "", type: "text" });
  }
  renderDebugFormTable();
}

function hasNativeFilePicker() {
  return Boolean(window.pywebview && window.pywebview.api && window.pywebview.api.pick_file);
}

async function pickDebugFormFile(idx) {
  if (!hasNativeFilePicker()) return;
  const chosen = await window.pywebview.api.pick_file();
  if (chosen) {
    dbgFormFields[idx].value = chosen;
    renderDebugFormTable();
  }
}

async function pickStepFormFile(idx, fIdx) {
  if (!hasNativeFilePicker()) return;
  const chosen = await window.pywebview.api.pick_file();
  if (chosen) {
    updateStepFormField(idx, fIdx, "value", chosen);
    renderSteps();
  }
}

async function pickUiUploadFile(idx) {
  if (!hasNativeFilePicker()) return;
  const chosen = await window.pywebview.api.pick_file();
  if (chosen) {
    currentCase.steps[idx].value = chosen;
    setCaseDirty(true);
    renderSteps();
    recordCaseChange();
  }
}

function renderDebugFormTable() {
  const tbody = document.getElementById("dbg-form-tbody");
  if (!tbody) return;
  const isMultipart = dbgBodyType === "form_data";
  const canBrowse = hasNativeFilePicker();
  tbody.innerHTML = dbgFormFields
    .map(
      (f, idx) => `<tr>
      <td><input value="${escapeHtml(f.key)}" placeholder="字段名" oninput="dbgFormFields[${idx}].key = this.value" /></td>
      ${
        isMultipart
          ? `<td><select onchange="dbgFormFields[${idx}].type = this.value; renderDebugFormTable();">
              <option value="text" ${f.type !== "file" ? "selected" : ""}>文本</option>
              <option value="file" ${f.type === "file" ? "selected" : ""}>文件</option>
            </select></td>`
          : ""
      }
      <td>
        <div style="display:flex;gap:6px;align-items:center;">
          <input value="${escapeHtml(f.value)}" placeholder="${f.type === "file" ? "本地文件绝对路径 (如 D:\\\\test.png)" : "字段值"}" oninput="dbgFormFields[${idx}].value = this.value" />
          ${isMultipart && f.type === "file" && canBrowse ? `<button class="btn btn-xs btn-outline" onclick="pickDebugFormFile(${idx})">浏览</button>` : ""}
        </div>
      </td>
      <td><button class="btn btn-xs btn-danger-outline" onclick="dbgFormFields.splice(${idx}, 1); renderDebugFormTable();">删</button></td>
    </tr>`
    )
    .join("");
}

function addDebugFormRow() {
  dbgFormFields.push({ key: "", value: "", type: "text" });
  renderDebugFormTable();
}

function getDebugHistory() {
  try {
    return JSON.parse(localStorage.getItem("TESTFLOW_DEBUG_HISTORY") || "[]");
  } catch {
    return [];
  }
}

function pushDebugHistory(entry) {
  try {
    const safeEntry = { ...entry };
    if (safeEntry.body !== null && safeEntry.body !== undefined) {
      const bodyStr = typeof safeEntry.body === "string" ? safeEntry.body : JSON.stringify(safeEntry.body);
      if (bodyStr.length > 32768) {
        safeEntry.body = bodyStr.slice(0, 32768) + "\n... [历史记录已截断]";
      }
    }
    const list = getDebugHistory();
    list.unshift(safeEntry);
    localStorage.setItem("TESTFLOW_DEBUG_HISTORY", JSON.stringify(list.slice(0, 20)));
  } catch {
    // ignore
  }
}

function openHistoryModal() {
  const listEl = document.getElementById("history-list");
  const list = getDebugHistory();
  if (!list.length) {
    listEl.innerHTML = `<div class="step-pane-hint" style="padding:12px 0;">暂无调试历史，发送一次请求后会自动记录在这里。</div>`;
  } else {
    listEl.innerHTML = list
      .map(
        (h, idx) => `<div class="history-item" onclick="loadHistoryItem(${idx})">
        <span class="badge ${h.status_code && h.status_code < 400 ? "badge-ok" : "badge-err"}">${escapeHtml(h.method)}</span>
        <span class="history-url">${escapeHtml(h.url)}</span>
        <span class="badge badge-info">${h.status_code || "ERR"}</span>
        <span class="step-pane-hint">${escapeHtml(h.time || "")}</span>
      </div>`
      )
      .join("");
  }
  document.getElementById("history-modal").classList.remove("hidden");
}

function closeHistoryModal() {
  document.getElementById("history-modal").classList.add("hidden");
}

function clearDebugHistory() {
  localStorage.removeItem("TESTFLOW_DEBUG_HISTORY");
  openHistoryModal();
  showToast("调试历史已清空");
}

function loadHistoryItem(idx) {
  const item = getDebugHistory()[idx];
  if (!item) return;
  document.getElementById("dbg-method").value = item.method || "GET";
  document.getElementById("dbg-url").value = item.url || "";
  document.getElementById("dbg-headers").value = JSON.stringify(item.headers || {}, null, 2);
  document.getElementById("dbg-params").value = JSON.stringify(item.params || {}, null, 2);
  dbgFormFields = Array.isArray(item.form_fields) ? JSON.parse(JSON.stringify(item.form_fields)) : [];
  switchDebugBodyType(item.body_type || "json");
  if (item.body !== null && item.body !== undefined) {
    document.getElementById("dbg-body").value =
      typeof item.body === "string" ? item.body : JSON.stringify(item.body, null, 2);
  } else {
    document.getElementById("dbg-body").value = "";
  }
  closeHistoryModal();
  showToast("已回填历史请求");
}

function switchRespTab(tab, btn) {
  activeRespTab = tab;
  document.querySelectorAll(".resp-tab").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  document.getElementById("dbg-response").classList.toggle("hidden", tab !== "body");
  document.getElementById("dbg-resp-headers").classList.toggle("hidden", tab !== "headers");
}

function formatDebugJson() {
  const ids = ["dbg-body", "dbg-headers", "dbg-params"];
  let formattedCount = 0;
  for (const id of ids) {
    const el = document.getElementById(id);
    const val = (el.value || "").trim();
    if (!val) continue;
    try {
      el.value = JSON.stringify(JSON.parse(val), null, 2);
      formattedCount++;
    } catch {
      // skip non-json text
    }
  }
  showToast(formattedCount ? "JSON 已格式化" : "当前无可格式化的 JSON 内容");
}

async function sendDebugRequest() {
  const btn = document.getElementById("dbg-send-btn");
  btn.disabled = true;
  btn.textContent = "请求中...";
  try {
    const headers = safeParseJson(document.getElementById("dbg-headers").value, {});
    const params = safeParseJson(document.getElementById("dbg-params").value, {});
    const rawBody = document.getElementById("dbg-body").value.trim();
    let body = null;
    if (rawBody) {
      if (dbgBodyType === "raw") {
        body = rawBody;
      } else {
        try {
          body = JSON.parse(rawBody);
        } catch {
          body = rawBody;
        }
      }
    }
    const payload = {
      env: document.getElementById("global-env-select").value,
      method: document.getElementById("dbg-method").value,
      url: document.getElementById("dbg-url").value.trim(),
      headers,
      params,
      body,
      body_type: dbgBodyType,
      form_fields: dbgFormFields,
      timeout: Number(document.getElementById("dbg-timeout")?.value) || 30,
    };
    const res = await apiFetch("/api/debug", { method: "POST", body: JSON.stringify(payload) });
    pushDebugHistory({
      ...payload,
      status_code: res.ok ? res.status_code : null,
      time: new Date().toLocaleTimeString(),
    });
    const meta = document.getElementById("dbg-meta");
    const pre = document.getElementById("dbg-response");
    const hdrPre = document.getElementById("dbg-resp-headers");
    if (!res.ok) {
      meta.innerHTML = `<span class="badge badge-err">请求异常</span>`;
      pre.textContent = res.error || "未知错误";
      hdrPre.textContent = "无";
      return;
    }
    const statusClass = res.status_code < 400 ? "badge-ok" : "badge-err";
    const bodyStr = typeof res.body === "string" ? res.body : JSON.stringify(res.body, null, 2);
    const sizeKb = (new Blob([bodyStr]).size / 1024).toFixed(1);
    meta.innerHTML = `<span class="badge ${statusClass}">HTTP ${res.status_code}</span><span class="badge badge-info">${res.elapsed_ms} ms</span><span class="badge badge-info">${sizeKb} KB</span>`;
    pre.textContent = bodyStr;
    hdrPre.textContent = JSON.stringify(res.headers || {}, null, 2);
  } catch (err) {
    showToast("参数格式错误: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "发送请求";
  }
}

async function copyDebugResponse() {
  const targetId = activeRespTab === "headers" ? "dbg-resp-headers" : "dbg-response";
  const text = document.getElementById(targetId).textContent || "";
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    showToast("内容已复制到剪贴板");
  } catch {
    showToast("复制失败，请手动选中复制");
  }
}

function openSaveStepModal() {
  const sel = document.getElementById("modal-target-case");
  sel.innerHTML =
    casesList
      .map((c) => `<option value="${escapeHtml(c.filename)}">${escapeHtml(c.name)} (${escapeHtml(c.filename)})</option>`)
      .join("") + `<option value="__NEW__">+ 新建一条用例...</option>`;
  document.getElementById("modal-step-name").value = `${document.getElementById("dbg-method").value} ${document.getElementById("dbg-url").value}`;
  document.getElementById("save-step-modal").classList.remove("hidden");
}

function closeSaveStepModal() {
  document.getElementById("save-step-modal").classList.add("hidden");
}

async function confirmSaveStepToCase() {
  try {
    const stepName = document.getElementById("modal-step-name").value.trim() || "接口请求";
    const target = document.getElementById("modal-target-case").value;
    const headers = safeParseJson(document.getElementById("dbg-headers").value, {});
    const params = safeParseJson(document.getElementById("dbg-params").value, {});
    const rawBody = document.getElementById("dbg-body").value.trim();
    const reqObj = {
      method: document.getElementById("dbg-method").value,
      url: document.getElementById("dbg-url").value.trim(),
      headers,
      params,
    };
    if (dbgBodyType === "form_urlencoded" || dbgBodyType === "form_data") {
      reqObj.body_type = dbgBodyType;
      reqObj.form_fields = JSON.parse(JSON.stringify(dbgFormFields.filter((f) => f.key && f.key.trim())));
    } else if (dbgBodyType === "raw") {
      if (rawBody) {
        reqObj.body_type = "raw";
        reqObj.body = rawBody;
      }
    } else if (rawBody) {
      try {
        reqObj.json = JSON.parse(rawBody);
      } catch {
        reqObj.body_type = "raw";
        reqObj.body = rawBody;
      }
    }
    const newStep = {
      type: "api",
      name: stepName,
      request: reqObj,
      extract: [],
      assertions: [{ type: "status_code", target: "", expected: 200 }],
    };

    if (target === "__NEW__") {
      const caseName = prompt("请输入新用例名称：", "新建接口用例") || "新建接口用例";
      const created = await apiFetch("/api/cases", {
        method: "POST",
        body: JSON.stringify({ name: caseName, description: "", steps: [newStep] }),
      });
      await loadCasesList(created.filename);
    } else {
      const detail = await apiFetch(`/api/cases/${encodeURIComponent(target)}`);
      detail.steps.push(newStep);
      await apiFetch(`/api/cases/${encodeURIComponent(target)}`, {
        method: "PUT",
        body: JSON.stringify(detail),
      });
      await loadCasesList(target);
    }
    closeSaveStepModal();
    switchTab("cases");
    showToast("已保存为用例步骤");
  } catch (err) {
    showToast("保存失败: " + err.message);
  }
}

// ---------- 用例列表与编排 ----------
function toggleSelectAllCases() {
  const checks = Array.from(document.querySelectorAll(".case-check"));
  if (!checks.length) return;
  const allChecked = checks.every((c) => c.checked);
  checks.forEach((c) => {
    c.checked = !allChecked;
  });
}

function triggerImportYaml() {
  const input = document.getElementById("import-yaml-input");
  input.value = "";
  input.click();
}

async function handleImportYamlFile(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  try {
    const content = await file.text();
    const res = await apiFetch("/api/cases/import_yaml", {
      method: "POST",
      body: JSON.stringify({ filename: file.name, content }),
    });
    await loadCasesList(res.filename);
    showToast(`已导入用例：${res.filename}`);
  } catch (err) {
    showToast("导入失败: " + err.message);
  }
}

function triggerImportCollection() {
  const input = document.getElementById("import-collection-input");
  input.value = "";
  input.click();
}

async function handleImportCollectionFile(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  try {
    const content = await file.text();
    const res = await apiFetch("/api/cases/import_collection", {
      method: "POST",
      body: JSON.stringify({ filename: file.name, content }),
    });
    await loadCasesList(res.filename);
    switchTab("cases");
    showToast(`已从 ${res.source_type} 导入 ${res.step_count} 个接口步骤`);
  } catch (err) {
    showToast("导入集合失败: " + err.message);
  }
}

async function exportCurrentCaseYaml() {
  if (!currentCase) return;
  await saveCurrentCase();
  const res = await apiFetch(`/api/cases/${encodeURIComponent(currentCase.filename)}/raw`);
  const blob = new Blob([res.content], { type: "text/yaml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = res.filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  showToast(`已导出 ${res.filename}`);
}

function filterCases() {
  const q = (document.getElementById("case-search")?.value || "").trim().toLowerCase();
  document.querySelectorAll(".case-item").forEach((el) => {
    const text = el.textContent.toLowerCase();
    el.classList.toggle("hidden", Boolean(q) && !text.includes(q));
  });
}

function renderCasesSidebarDom() {
  const checkedSet = new Set(
    Array.from(document.querySelectorAll(".case-check:checked")).map((c) => c.value)
  );
  const hadExistingChecks = document.querySelectorAll(".case-check").length > 0;
  const listEl = document.getElementById("case-list");
  listEl.innerHTML = casesList
    .map((c) => {
      const r = caseRunResultsMap[c.filename];
      const stIcon = r
        ? r.status === "passed"
          ? `<span class="case-status-dot case-status-pass" title="最近一次运行通过">✓</span>`
          : `<span class="case-status-dot case-status-fail" title="最近一次运行失败">✗</span>`
        : "";
      const isChecked = !hadExistingChecks || checkedSet.has(c.filename);
      return `<div class="case-item ${currentCase && currentCase.filename === c.filename ? "active" : ""}" onclick="selectCase('${escapeHtml(c.filename)}')">
        <input type="checkbox" class="case-check" value="${escapeHtml(c.filename)}" onclick="event.stopPropagation()" ${isChecked ? "checked" : ""} />
        <div class="case-item-info">
          <div class="case-item-title">${escapeHtml(c.name)}</div>
          <div class="case-item-sub">${escapeHtml(c.filename)} · ${c.step_count} 步</div>
        </div>
        ${stIcon}
      </div>`;
    })
    .join("");
  const countEl = document.getElementById("case-count-text");
  if (countEl) countEl.textContent = `共 ${casesList.length} 条`;
  filterCases();
}

async function refreshCasesSidebarOnly() {
  const data = await apiFetch("/api/cases");
  casesList = data.cases || [];
  renderCasesSidebarDom();
}

async function loadCasesList(selectFilename = null, keepHistory = false) {
  const data = await apiFetch("/api/cases");
  casesList = data.cases || [];
  renderCasesSidebarDom();

  const target = selectFilename || (currentCase && currentCase.filename) || (casesList[0] && casesList[0].filename);
  if (target) {
    await selectCase(target, false, keepHistory);
  }
}

async function selectCase(filename, force = false, keepHistory = false) {
  if (!force && caseDirty && currentCase && currentCase.filename !== filename) {
    if (!confirm(`用例「${currentCase.name}」有未保存修改，确定放弃修改并切换吗？`)) {
      return;
    }
  }
  currentCase = await apiFetch(`/api/cases/${encodeURIComponent(filename)}`);
  apiStepTabMap = {};
  stepCollapseMap = {};
  setCaseDirty(false);
  document.querySelectorAll(".case-item").forEach((el) => {
    const chk = el.querySelector(".case-check");
    el.classList.toggle("active", chk && chk.value === filename);
  });
  document.getElementById("case-name").value = currentCase.name || "";
  document.getElementById("case-desc").value = currentCase.description || "";
  renderSteps();
  if (!keepHistory) {
    resetCaseHistory();
  } else {
    caseSavedSnapshot = captureCaseSnapshot();
    caseCurrentSnapshot = caseSavedSnapshot;
    updateCaseHistoryButtons();
  }
}

async function createNewCase() {
  const name = prompt("请输入新用例名称：", "新自动化用例");
  if (!name || !name.trim()) return;
  try {
    const created = await apiFetch("/api/cases", {
      method: "POST",
      body: JSON.stringify({ name: name.trim(), description: "", steps: [] }),
    });
    await loadCasesList(created.filename);
    showToast("已创建新用例");
  } catch (err) {
    showToast("创建用例失败: " + err.message);
  }
}

async function duplicateCurrentCase() {
  if (!currentCase) return;
  try {
    const copyName = `${currentCase.name}_副本`;
    const cleanSteps = JSON.parse(JSON.stringify(currentCase.steps || []));
    cleanSteps.forEach((s) => {
      if (s.request && s.request._json_draft !== undefined) delete s.request._json_draft;
    });
    const created = await apiFetch("/api/cases", {
      method: "POST",
      body: JSON.stringify({
        name: copyName,
        description: currentCase.description || "",
        steps: cleanSteps,
      }),
    });
    await loadCasesList(created.filename);
    showToast("已复制用例");
  } catch (err) {
    showToast("复制用例失败: " + err.message);
  }
}

async function deleteCurrentCase() {
  if (!currentCase) return;
  if (!confirm(`确定删除用例「${currentCase.name}」吗？`)) return;
  try {
    await apiFetch(`/api/cases/${encodeURIComponent(currentCase.filename)}`, { method: "DELETE" });
    currentCase = null;
    await loadCasesList();
    showToast("用例已删除");
  } catch (err) {
    showToast("删除用例失败: " + err.message);
  }
}

function normalizeExtractsForUi(extract) {
  if (Array.isArray(extract)) return extract;
  if (extract && typeof extract === "object") {
    return Object.entries(extract).map(([name, path]) => ({ name, path }));
  }
  return [];
}

function renderSteps() {
  const container = document.getElementById("steps-container");
  if (!currentCase || !currentCase.steps.length) {
    container.innerHTML = `<div class="sidebar-tip">当前用例暂无步骤，请点击下方按钮添加接口或 UI 步骤。</div>`;
    return;
  }
  container.innerHTML = currentCase.steps.map((step, idx) => renderStepCard(step, idx)).join("");
}

function toggleStepCollapse(idx) {
  stepCollapseMap[idx] = !stepCollapseMap[idx];
  renderSteps();
}

function switchApiStepTab(idx, tab) {
  apiStepTabMap[idx] = tab;
  renderSteps();
}

function getApiKvRows(req, field) {
  const obj = req[field];
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return [];
  return Object.entries(obj);
}

function addApiKvRow(idx, field) {
  const req = (currentCase.steps[idx].request = currentCase.steps[idx].request || {});
  const obj = req[field] && typeof req[field] === "object" ? { ...req[field] } : {};
  let key = "new_key";
  let suffix = 1;
  while (Object.prototype.hasOwnProperty.call(obj, key)) {
    key = `new_key_${suffix++}`;
  }
  obj[key] = "";
  req[field] = obj;
  setCaseDirty(true);
  renderSteps();
  recordCaseChange();
}

function updateApiKvRow(idx, field, rowIdx, part, val) {
  const req = (currentCase.steps[idx].request = currentCase.steps[idx].request || {});
  const entries = getApiKvRows(req, field);
  if (!entries[rowIdx]) return;
  if (part === "key") {
    entries[rowIdx][0] = val;
  } else {
    entries[rowIdx][1] = val;
  }
  const rebuilt = {};
  for (const [k, v] of entries) {
    rebuilt[String(k)] = v;
  }
  req[field] = rebuilt;
  setCaseDirty(true);
  recordCaseChange();
}

function removeApiKvRow(idx, field, rowIdx) {
  const req = (currentCase.steps[idx].request = currentCase.steps[idx].request || {});
  const entries = getApiKvRows(req, field);
  entries.splice(rowIdx, 1);
  const rebuilt = {};
  for (const [k, v] of entries) {
    if (String(k).trim()) rebuilt[String(k).trim()] = v;
  }
  req[field] = rebuilt;
  setCaseDirty(true);
  renderSteps();
  recordCaseChange();
}

function clearApiKvRows(idx, field) {
  const req = (currentCase.steps[idx].request = currentCase.steps[idx].request || {});
  req[field] = {};
  setCaseDirty(true);
  renderSteps();
  recordCaseChange();
}

function formatStepBodyJson(idx) {
  const req = (currentCase.steps[idx].request = currentCase.steps[idx].request || {});
  if (req._json_draft !== undefined) {
    try {
      req.json = JSON.parse(req._json_draft);
      delete req._json_draft;
      setCaseDirty(true);
      renderSteps();
      recordCaseChange();
      showToast("JSON 已格式化");
      return;
    } catch {
      showToast("当前 Body 非合法 JSON，无法格式化");
      return;
    }
  }
  if (req.json !== undefined && typeof req.json === "object") {
    renderSteps();
    showToast("JSON 已格式化");
    return;
  }
  if (req.body && typeof req.body === "string") {
    try {
      req.json = JSON.parse(req.body);
      delete req.body;
      setCaseDirty(true);
      renderSteps();
      recordCaseChange();
      showToast("JSON 已格式化");
      return;
    } catch {
      // ignore
    }
  }
  showToast("当前 Body 非合法 JSON 或已格式化");
}

function setStepBodyType(idx, btype) {
  const req = (currentCase.steps[idx].request = currentCase.steps[idx].request || {});
  req.body_type = btype;
  if ((btype === "form_urlencoded" || btype === "form_data") && (!Array.isArray(req.form_fields) || !req.form_fields.length)) {
    req.form_fields = [{ key: "", value: "", type: btype === "form_data" ? "file" : "text" }];
  }
  setCaseDirty(true);
  renderSteps();
  recordCaseChange();
}

function updateStepRawBody(idx, val) {
  const req = (currentCase.steps[idx].request = currentCase.steps[idx].request || {});
  delete req.json;
  req.body_type = "raw";
  req.body = val;
  setCaseDirty(true);
  recordCaseChange();
}

function addStepFormField(idx) {
  const req = (currentCase.steps[idx].request = currentCase.steps[idx].request || {});
  req.form_fields = Array.isArray(req.form_fields) ? req.form_fields : [];
  req.form_fields.push({ key: "", value: "", type: "text" });
  setCaseDirty(true);
  renderSteps();
  recordCaseChange();
}

function updateStepFormField(idx, fIdx, field, val) {
  const req = (currentCase.steps[idx].request = currentCase.steps[idx].request || {});
  if (Array.isArray(req.form_fields) && req.form_fields[fIdx]) {
    req.form_fields[fIdx][field] = val;
    setCaseDirty(true);
    recordCaseChange();
  }
}

function removeStepFormField(idx, fIdx) {
  const req = (currentCase.steps[idx].request = currentCase.steps[idx].request || {});
  if (Array.isArray(req.form_fields)) {
    req.form_fields.splice(fIdx, 1);
    setCaseDirty(true);
    renderSteps();
    recordCaseChange();
  }
}

function collapseAllSteps(collapsed) {
  if (!currentCase || !currentCase.steps) return;
  currentCase.steps.forEach((_, idx) => {
    stepCollapseMap[idx] = Boolean(collapsed);
  });
  renderSteps();
}

function getStepRunResult(idx) {
  if (!currentCase) return null;
  const cr = caseRunResultsMap[currentCase.filename];
  if (!cr || !Array.isArray(cr.steps)) return null;
  return cr.steps[idx] || null;
}

function switchStepResultSubTab(idx, sub) {
  stepResultSubTabMap[idx] = sub;
  renderSteps();
}

async function copyStepResultText(idx) {
  const sr = getStepRunResult(idx);
  if (!sr) return;
  const sub = stepResultSubTabMap[idx] || "resp";
  let payload = sr.response?.body ?? sr.error ?? "";
  if (sub === "req") payload = sr.request || {};
  else if (sub === "headers") payload = sr.response?.headers || {};
  const txt = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
  try {
    await navigator.clipboard.writeText(txt);
    showToast("已复制到剪贴板");
  } catch {
    showToast("复制失败");
  }
}

async function runSingleApiStep(idx) {
  if (!currentCase || !currentCase.steps[idx]) return;
  const step = currentCase.steps[idx];
  const req = step.request || {};
  if (req._json_draft !== undefined) {
    const trimmed = req._json_draft.trim();
    if (!trimmed) {
      delete req.json;
      delete req._json_draft;
    } else {
      try {
        req.json = JSON.parse(trimmed);
        delete req._json_draft;
      } catch {
        showToast("当前步骤 Body 不是合法 JSON，请先修正后再试跑");
        return;
      }
    }
  }
  const payload = {
    env: document.getElementById("global-env-select").value,
    method: (req.method || "GET").toUpperCase(),
    url: req.url || "",
    headers: req.headers || {},
    params: req.params || {},
    body: req.json !== undefined ? req.json : req.body ?? null,
    body_type: req.body_type || "json",
    form_fields: req.form_fields || [],
    timeout: Number(step.timeout ?? req.timeout ?? 15),
  };
  showToast(`正在试跑 #${idx + 1}...`);
  try {
    const res = await apiFetch("/api/debug", { method: "POST", body: JSON.stringify(payload) });
    const cname = currentCase.filename;
    if (!caseRunResultsMap[cname]) {
      caseRunResultsMap[cname] = { filename: cname, status: "passed", steps: [] };
    }
    caseRunResultsMap[cname].steps[idx] = {
      index: idx + 1,
      type: "api",
      name: step.name || `步骤 ${idx + 1}`,
      status: res.ok && res.status_code < 400 ? "passed" : res.ok ? "passed" : "failed",
      duration_ms: res.elapsed_ms || 0,
      error: res.ok ? "" : res.error || "请求异常",
      request: payload,
      response: res.ok
        ? { status_code: res.status_code, elapsed_ms: res.elapsed_ms, headers: res.headers, body: res.body }
        : null,
      extracted: {},
      assertions: [],
    };
    apiStepTabMap[idx] = "result";
    stepCollapseMap[idx] = false;
    renderSteps();
    showToast(res.ok ? `试跑完成: HTTP ${res.status_code} (${res.elapsed_ms}ms)` : "试跑异常");
  } catch (err) {
    showToast("试跑失败: " + err.message);
  }
}

function renderApiStepResultPane(idx, sr) {
  if (!sr) {
    return `<div class="step-tab-pane"><div class="step-pane-hint" style="padding:10px 0;">暂无运行结果。点击当前步骤「▶ 试跑」或上方「▶ 运行当前用例」后可在此直接查看请求、响应与断言对比。</div></div>`;
  }
  const sub = stepResultSubTabMap[idx] || "resp";
  const resp = sr.response || {};
  const sc = resp.status_code;
  const scBadge = sc ? `<span class="badge ${sc < 400 ? "badge-ok" : "badge-err"}">HTTP ${sc}</span>` : "";
  const durBadge = `<span class="badge badge-info">${sr.duration_ms || resp.elapsed_ms || 0} ms</span>`;

  let bodyDisplay = "";
  if (sub === "resp") {
    const b = resp.body;
    bodyDisplay = b !== undefined ? (typeof b === "string" ? b : JSON.stringify(b, null, 2)) : sr.error || "无响应内容";
  } else if (sub === "req") {
    bodyDisplay = JSON.stringify(sr.request || {}, null, 2);
  } else {
    bodyDisplay = JSON.stringify(resp.headers || {}, null, 2);
  }

  const asserts = sr.assertions || [];
  const extracted = sr.extracted || {};
  const hasExtracts = Object.keys(extracted).length > 0;

  return `<div class="step-tab-pane">
    <div class="step-result-box">
      ${sr.error ? `<div class="ui-hint" style="background:#fef2f2;border-color:#fecaca;color:#991b1b;"><strong>失败原因：</strong>${escapeHtml(sr.error)}</div>` : ""}
      <div class="step-result-meta">
        ${scBadge}
        ${durBadge}
        <div class="sub-tabs" style="margin:0;">
          <button class="sub-tab ${sub === "resp" ? "active" : ""}" onclick="switchStepResultSubTab(${idx}, 'resp')">响应体</button>
          <button class="sub-tab ${sub === "req" ? "active" : ""}" onclick="switchStepResultSubTab(${idx}, 'req')">实际请求</button>
          <button class="sub-tab ${sub === "headers" ? "active" : ""}" onclick="switchStepResultSubTab(${idx}, 'headers')">响应头</button>
        </div>
        <button class="btn btn-xs btn-outline" style="margin-left:auto;" onclick="copyStepResultText(${idx})">复制内容</button>
      </div>
      <pre class="step-result-pre">${escapeHtml(bodyDisplay)}</pre>
      ${hasExtracts ? `<div class="step-pane-hint"><strong>本次提取变量：</strong>${escapeHtml(JSON.stringify(extracted))}</div>` : ""}
      ${
        asserts.length
          ? `<table class="step-assert-tbl">
              <thead><tr><th>断言类型</th><th>目标</th><th>期望值</th><th>实际值</th><th>结果</th></tr></thead>
              <tbody>
                ${asserts
                  .map(
                    (a) => `<tr>
                    <td>${escapeHtml(a.type)}</td>
                    <td>${escapeHtml(a.target)}</td>
                    <td>${escapeHtml(a.expected)}</td>
                    <td>${escapeHtml(typeof a.actual === "object" ? JSON.stringify(a.actual) : a.actual)}</td>
                    <td style="font-weight:700;color:${a.passed ? "var(--success)" : "var(--danger)"};">${a.passed ? "通过" : "失败"}</td>
                  </tr>`
                  )
                  .join("")}
              </tbody>
            </table>`
          : ""
      }
    </div>
  </div>`;
}

function renderStepSummary(step, isApi) {
  if (isApi) {
    const req = step.request || {};
    const m = (req.method || "GET").toUpperCase();
    const u = req.url || "(未填写 URL)";
    const asserts = (step.assertions || []).length;
    const extracts = normalizeExtractsForUi(step.extract).length;
    return `${m} ${u}  ·  提取 ${extracts} 项 · 断言 ${asserts} 项`;
  }
  const act = (step.action || "open").toLowerCase();
  const target = step.locator || step.key || step.value || "";
  return `${act}${target ? " → " + target : ""}`;
}

function renderStepCard(step, idx) {
  const isApi = (step.type || "api").toLowerCase() === "api";
  const enabled = step.enabled !== false;
  const collapsed = Boolean(stepCollapseMap[idx]);
  const sr = getStepRunResult(idx);
  const resBadge = sr
    ? sr.status === "passed"
      ? `<span class="step-res-badge step-res-ok">通过 · ${sr.duration_ms ?? 0}ms</span>`
      : sr.status === "skipped"
        ? `<span class="step-res-badge step-res-skip">已跳过</span>`
        : `<span class="step-res-badge step-res-err">失败 · ${sr.duration_ms ?? 0}ms</span>`
    : "";

  const header = `<div class="step-card-header">
    <button class="step-collapse-btn" title="${collapsed ? "展开步骤" : "折叠步骤"}" onclick="toggleStepCollapse(${idx})">${collapsed ? "▸" : "▾"}</button>
    <span class="step-type-tag ${isApi ? "tag-api" : "tag-ui"}">${isApi ? "API" : "UI"} #${idx + 1}</span>
    <input class="step-name-input" value="${escapeHtml(step.name || "")}" oninput="updateStepFieldLive(${idx}, 'name', this.value)" onchange="recordCaseChange()" placeholder="步骤名称" />
    ${resBadge}
    ${isApi ? `<button class="btn btn-sm btn-outline" title="单独试跑此接口" onclick="runSingleApiStep(${idx})">▶ 试跑</button>` : ""}
    <label class="step-enable-toggle" title="取消勾选将在运行时跳过此步骤">
      <input type="checkbox" ${enabled ? "checked" : ""} onchange="toggleStepEnabled(${idx}, this.checked)" />
      <span>启用</span>
    </label>
    <button class="btn btn-sm btn-outline" onclick="duplicateStep(${idx})">复制</button>
    <button class="btn btn-sm btn-outline" onclick="moveStep(${idx}, -1)">↑</button>
    <button class="btn btn-sm btn-outline" onclick="moveStep(${idx}, 1)">↓</button>
    <button class="btn btn-sm btn-danger-outline" onclick="removeStep(${idx})">删除</button>
  </div>`;

  if (collapsed) {
    return `<div class="step-card ${isApi ? "step-card-api" : "step-card-ui"} ${enabled ? "" : "step-disabled"}">
      ${header}
      <div class="step-summary">${escapeHtml(renderStepSummary(step, isApi))}</div>
    </div>`;
  }

  if (isApi) {
    const req = step.request || {};
    const method = (req.method || "GET").toUpperCase();
    const extracts = normalizeExtractsForUi(step.extract);
    const assertions = step.assertions || [];
    const headerRows = getApiKvRows(req, "headers");
    const paramRows = getApiKvRows(req, "params");
    const bodyText = req._json_draft !== undefined ? req._json_draft : req.json !== undefined ? JSON.stringify(req.json, null, 2) : req.body ? String(req.body) : "";
    const stepBodyType = (req.body_type || "json").toLowerCase();
    const formFields = Array.isArray(req.form_fields) ? req.form_fields : [];
    const hasBodyContent = stepBodyType === "form_urlencoded" || stepBodyType === "form_data" ? formFields.length > 0 : Boolean(bodyText);
    const timeoutVal = step.timeout ?? req.timeout ?? 15;
    const activeTab = apiStepTabMap[idx] || "body";

    const renderKvPane = (field, rows, keyPh, valPh, addText) => `
      <div class="step-tab-pane">
        <div class="step-pane-toolbar">
          <span class="step-pane-hint">共 ${rows.length} 项（修改后自动同步）</span>
          <div style="display:flex;gap:6px;">
            ${rows.length ? `<button class="btn btn-xs btn-outline" onclick="clearApiKvRows(${idx}, '${field}')">清空</button>` : ""}
            <button class="btn btn-xs btn-outline" onclick="addApiKvRow(${idx}, '${field}')">${addText}</button>
          </div>
        </div>
        ${
          rows.length
            ? `<table class="kv-mini-table">
              <thead><tr><th width="34%">Key</th><th>Value</th><th width="54">操作</th></tr></thead>
              <tbody>
                ${rows
                  .map(
                    ([k, v], rIdx) => `<tr>
                    <td><input value="${escapeHtml(k)}" placeholder="${keyPh}" oninput="updateApiKvRowLive(${idx}, '${field}', ${rIdx}, 'key', this.value)" onchange="recordCaseChange()" /></td>
                    <td><input value="${escapeHtml(typeof v === "string" ? v : JSON.stringify(v))}" placeholder="${valPh}" oninput="updateApiKvRowLive(${idx}, '${field}', ${rIdx}, 'val', this.value)" onchange="recordCaseChange()" /></td>
                    <td><button class="btn btn-xs btn-danger-outline" onclick="removeApiKvRow(${idx}, '${field}', ${rIdx})">删</button></td>
                  </tr>`
                  )
                  .join("")}
              </tbody>
            </table>`
            : `<div class="step-pane-hint" style="padding:6px 0;">暂无配置，点击右侧按钮添加。</div>`
        }
      </div>`;

    let paneHtml = "";
    if (activeTab === "body") {
      const isForm = stepBodyType === "form_urlencoded" || stepBodyType === "form_data";
      const isMultipart = stepBodyType === "form_data";
      const canBrowse = hasNativeFilePicker();
      const typeBarHtml = `<div class="body-type-bar" style="margin-bottom:4px;">
        <label><input type="radio" name="step-btype-${idx}" value="json" ${stepBodyType === "json" ? "checked" : ""} onchange="setStepBodyType(${idx}, 'json')" /> JSON</label>
        <label><input type="radio" name="step-btype-${idx}" value="form_urlencoded" ${stepBodyType === "form_urlencoded" ? "checked" : ""} onchange="setStepBodyType(${idx}, 'form_urlencoded')" /> x-www-form-urlencoded</label>
        <label><input type="radio" name="step-btype-${idx}" value="form_data" ${stepBodyType === "form_data" ? "checked" : ""} onchange="setStepBodyType(${idx}, 'form_data')" /> form-data（支持文件）</label>
        <label><input type="radio" name="step-btype-${idx}" value="raw" ${stepBodyType === "raw" ? "checked" : ""} onchange="setStepBodyType(${idx}, 'raw')" /> Raw</label>
      </div>`;

      if (isForm) {
        paneHtml = `<div class="step-tab-pane">
          ${typeBarHtml}
          <div class="step-pane-toolbar">
            <span class="step-pane-hint">${isMultipart ? "上传文件时类型选「文件」，Value 填绝对路径或点「浏览」" : "表单键值对（支持 {{变量}}）"}</span>
            <button class="btn btn-xs btn-outline" onclick="addStepFormField(${idx})">+ 添加字段</button>
          </div>
          ${
            formFields.length
              ? `<table class="kv-mini-table">
                <thead><tr><th width="28%">Key</th>${isMultipart ? '<th width="96">类型</th>' : ""}<th>Value / 文件路径</th><th width="54">操作</th></tr></thead>
                <tbody>
                  ${formFields
                    .map(
                      (f, fIdx) => `<tr>
                      <td><input value="${escapeHtml(f.key)}" placeholder="字段名 (如 file)" oninput="updateStepFormFieldLive(${idx}, ${fIdx}, 'key', this.value)" onchange="recordCaseChange()" /></td>
                      ${
                        isMultipart
                          ? `<td><select onchange="updateStepFormField(${idx}, ${fIdx}, 'type', this.value); renderSteps();">
                              <option value="text" ${f.type !== "file" ? "selected" : ""}>文本</option>
                              <option value="file" ${f.type === "file" ? "selected" : ""}>文件</option>
                            </select></td>`
                          : ""
                      }
                      <td>
                        <div style="display:flex;gap:6px;align-items:center;">
                          <input value="${escapeHtml(f.value)}" placeholder="${f.type === "file" ? "本地文件绝对路径" : "字段值"}" oninput="updateStepFormFieldLive(${idx}, ${fIdx}, 'value', this.value)" onchange="recordCaseChange()" />
                          ${isMultipart && f.type === "file" && canBrowse ? `<button class="btn btn-xs btn-outline" onclick="pickStepFormFile(${idx}, ${fIdx})">浏览</button>` : ""}
                        </div>
                      </td>
                      <td><button class="btn btn-xs btn-danger-outline" onclick="removeStepFormField(${idx}, ${fIdx})">删</button></td>
                    </tr>`
                    )
                    .join("")}
                </tbody>
              </table>`
              : `<div class="step-pane-hint" style="padding:6px 0;">暂无字段，点击右上角「+ 添加字段」。</div>`
          }
        </div>`;
      } else {
        paneHtml = `<div class="step-tab-pane">
          ${typeBarHtml}
          <div class="step-pane-toolbar">
            <span class="step-pane-hint">${stepBodyType === "raw" ? "纯文本请求体（支持 {{变量}} 与动态函数）" : "支持 {{变量}} 与 {{$timestamp}} / {{$uuid}} 等动态函数"}</span>
            ${stepBodyType === "raw" ? "" : `<button class="btn btn-xs btn-outline" onclick="formatStepBodyJson(${idx})">格式化 JSON</button>`}
          </div>
          <div class="step-field step-field-full">
            <textarea rows="5" placeholder='${stepBodyType === "raw" ? "请输入原始请求体文本..." : '{"username": "{{username}}", "password": "{{password}}"}'}' oninput="${stepBodyType === "raw" ? `updateStepRawBodyLive(${idx}, this.value)` : `updateApiReqJsonLive(${idx}, 'json', this.value)`}" onchange="${stepBodyType === "raw" ? `recordCaseChange()` : `validateAndCommitApiJson(${idx}, 'json', this.value)`}">${escapeHtml(bodyText)}</textarea>
          </div>
        </div>`;
      }
    } else if (activeTab === "headers") {
      paneHtml = renderKvPane("headers", headerRows, "Header 名 (如 Authorization)", "Header 值 (如 Bearer {{token}})", "+ 添加 Header");
    } else if (activeTab === "params") {
      paneHtml = renderKvPane("params", paramRows, "参数名 (如 page)", "参数值 (如 1)", "+ 添加参数");
    } else if (activeTab === "extract") {
      paneHtml = `<div class="step-tab-pane">
        <div class="step-pane-toolbar">
          <span class="step-pane-hint">支持 JSONPath（$.data.token）、header:Set-Cookie、regex:token=(\\w+)</span>
          <button class="btn btn-xs btn-outline" onclick="addExtractRow(${idx})">+ 提取变量</button>
        </div>
        ${
          extracts.length
            ? extracts
                .map(
                  (ex, eIdx) => `<div class="mini-row">
                    <input class="extract-name-input" value="${escapeHtml(ex.name)}" placeholder="变量名 (如 token)" oninput="updateExtractLive(${idx}, ${eIdx}, 'name', this.value)" onchange="recordCaseChange()" />
                    <input class="extract-path-input" value="${escapeHtml(ex.path)}" placeholder="提取表达式 (如 $.data.token)" oninput="updateExtractLive(${idx}, ${eIdx}, 'path', this.value)" onchange="recordCaseChange()" />
                    <button class="btn btn-xs btn-danger-outline" onclick="removeExtract(${idx}, ${eIdx})">删</button>
                  </div>`
                )
                .join("")
            : `<div class="step-pane-hint" style="padding:6px 0;">暂无提取变量，点击右侧按钮添加。</div>`
        }
      </div>`;
    } else if (activeTab === "assert") {
      paneHtml = `<div class="step-tab-pane">
        <div class="step-pane-toolbar">
          <span class="step-pane-hint">任意一条断言不满足即判定该步骤失败</span>
          <button class="btn btn-xs btn-outline" onclick="addAssertRow(${idx})">+ 添加断言</button>
        </div>
        ${
          assertions.length
            ? assertions
                .map((as, aIdx) => {
                  const needTarget = ["json_equals", "json_not_equals", "json_contains", "json_exists", "json_gt", "json_lt", "header_contains"].includes(as.type);
                  const needExpected = as.type !== "json_exists";
                  const targetPlaceholder = as.type === "header_contains" ? "响应头名 (如 Content-Type)" : "JSON 路径 (如 $.code)";
                  const expectedPlaceholder = as.type === "response_time_lt" ? "耗时上限 (ms，如 500)" : as.type === "regex_match" ? "正则表达式" : "期望值";
                  return `<div class="mini-row">
                    <select class="assert-type-select" onchange="updateAssertType(${idx}, ${aIdx}, this.value)">
                      ${ASSERT_TYPES.map((t) => `<option value="${t.value}" ${as.type === t.value ? "selected" : ""}>${t.label}</option>`).join("")}
                    </select>
                    ${needTarget ? `<input class="assert-input" value="${escapeHtml(as.target || "")}" placeholder="${targetPlaceholder}" oninput="updateAssertLive(${idx}, ${aIdx}, 'target', this.value)" onchange="recordCaseChange()" />` : ""}
                    ${needExpected ? `<input class="assert-input" value="${escapeHtml(as.expected ?? "")}" placeholder="${expectedPlaceholder}" oninput="updateAssertLive(${idx}, ${aIdx}, 'expected', this.value)" onchange="recordCaseChange()" />` : ""}
                    <button class="btn btn-xs btn-danger-outline" onclick="removeAssert(${idx}, ${aIdx})">删</button>
                  </div>`;
                })
                .join("")
            : `<div class="step-pane-hint" style="padding:6px 0;">暂无断言规则，点击右侧按钮添加。</div>`
        }
      </div>`;
    } else if (activeTab === "result") {
      paneHtml = renderApiStepResultPane(idx, sr);
    }

    return `<div class="step-card step-card-api ${enabled ? "" : "step-disabled"}">${header}
      <div class="step-body">
        <div class="step-row">
          <div class="step-field step-field-method">
            <label>请求方法</label>
            <select class="method-badge-${method}" onchange="updateApiReq(${idx}, 'method', this.value); renderSteps();">
              ${["GET", "POST", "PUT", "DELETE", "PATCH"].map((m) => `<option ${method === m ? "selected" : ""}>${m}</option>`).join("")}
            </select>
          </div>
          <div class="step-field step-field-grow">
            <label>接口 URL（支持 {{变量}} 与动态函数）</label>
            <input value="${escapeHtml(req.url || "")}" placeholder="{{base_url}}/api/..." oninput="updateApiReqLive(${idx}, 'url', this.value)" onchange="recordCaseChange()" />
          </div>
          <div class="step-field step-field-timeout">
            <label>超时(秒)</label>
            <input type="number" min="1" value="${escapeHtml(timeoutVal)}" oninput="updateStepFieldLive(${idx}, 'timeout', Number(this.value) || 15)" onchange="recordCaseChange()" />
          </div>
        </div>
        <div class="step-tabs">
          <button class="step-tab-btn ${activeTab === "body" ? "active" : ""}" onclick="switchApiStepTab(${idx}, 'body')">Body${hasBodyContent ? " ●" : ""}</button>
          <button class="step-tab-btn ${activeTab === "headers" ? "active" : ""}" onclick="switchApiStepTab(${idx}, 'headers')">Headers (${headerRows.length})</button>
          <button class="step-tab-btn ${activeTab === "params" ? "active" : ""}" onclick="switchApiStepTab(${idx}, 'params')">Params (${paramRows.length})</button>
          <button class="step-tab-btn ${activeTab === "extract" ? "active" : ""}" onclick="switchApiStepTab(${idx}, 'extract')">提取变量 (${extracts.length})</button>
          <button class="step-tab-btn ${activeTab === "assert" ? "active" : ""}" onclick="switchApiStepTab(${idx}, 'assert')">断言校验 (${assertions.length})</button>
          <button class="step-tab-btn ${activeTab === "result" ? "active" : ""}" onclick="switchApiStepTab(${idx}, 'result')">运行结果${sr ? (sr.status === "passed" ? " ●" : " ✗") : ""}</button>
        </div>
        ${paneHtml}
      </div>
    </div>`;
  }

  const action = (step.action || "open").toLowerCase();
  const BY_ACTIONS = [
    "click", "double_click", "right_click", "hover",
    "input", "clear", "press_key", "select_option", "upload_file", "scroll_to",
    "wait_element", "switch_iframe",
    "assert_element", "assert_element_text", "assert_element_hidden",
    "get_text",
  ];
  const LOCATOR_ACTIONS = [...BY_ACTIONS, "set_local_storage", "set_cookie"];
  const VALUE_ACTIONS = [
    "open", "input", "press_key", "select_option", "upload_file", "scroll_to",
    "wait", "switch_tab", "handle_alert",
    "assert_text", "assert_title", "assert_url", "assert_element_text",
    "get_text", "set_local_storage", "set_cookie", "execute_js",
  ];

  const showBy = BY_ACTIONS.includes(action);
  const showLocator = LOCATOR_ACTIONS.includes(action);
  const showValue = VALUE_ACTIONS.includes(action);
  const showTimeout = !["wait", "screenshot", "refresh", "back", "forward"].includes(action);

  const locatorLabel =
    action === "set_local_storage"
      ? "LocalStorage Key"
      : action === "set_cookie"
        ? "Cookie 名称"
        : action === "switch_iframe"
          ? "iframe 定位（留空或填 default 切回主文档）"
          : action === "press_key" || action === "scroll_to"
            ? "元素定位表达式（可选，留空对全局生效）"
            : "元素定位表达式";

  const locatorPlaceholder =
    action === "set_local_storage"
      ? "例如：token"
      : action === "set_cookie"
        ? "例如：session_id"
        : "例如：#login-btn 或 //button[text()='登录']";

  const valueLabelMap = {
    open: "目标网址 (URL)",
    input: "输入文本",
    press_key: "按键名称",
    select_option: "选项文本或 Value",
    upload_file: "本地文件路径",
    scroll_to: "滚动位置（无定位时有效）",
    wait: "等待秒数",
    switch_tab: "标签页索引",
    handle_alert: "弹窗处理方式",
    assert_text: "期望包含的页面文本",
    assert_title: "期望包含的网页标题",
    assert_url: "期望包含的网址片段",
    assert_element_text: "期望元素包含的文本",
    get_text: "存入的变量名",
    set_local_storage: "写入的值",
    set_cookie: "Cookie 值",
    execute_js: "JavaScript 代码",
  };
  const valuePlaceholderMap = {
    open: "例如：{{base_url}}/demo/page",
    input: "例如：{{username}} 或 {{$random_str(6)}}",
    press_key: "例如：Enter / Tab / Escape / ArrowDown",
    select_option: "例如：已支付",
    upload_file: "例如：D:\\files\\test.png",
    scroll_to: "填 top / bottom 或像素如 500",
    wait: "例如：2",
    switch_tab: "例如：-1（最新标签页）或 0（第一个）",
    handle_alert: "填 accept（确认）或 dismiss（取消）",
    assert_text: "例如：{{order_no}}",
    assert_title: "例如：订单中心",
    assert_url: "例如：/dashboard",
    assert_element_text: "例如：登录成功",
    get_text: "例如：order_id（后续用 {{order_id}} 引用）",
    set_local_storage: "例如：{{token}}",
    set_cookie: "例如：{{token}}",
    execute_js: "例如：window.scrollTo(0, 300);",
  };

  const hintMap = {
    refresh: "刷新当前浏览器页面。",
    back: "浏览器后退到上一页。",
    forward: "浏览器前进到下一页。",
    close_tab: "关闭当前标签页并自动切回上一个可用标签页。",
    screenshot: "执行此步骤时将自动截取当前页面全屏截图并存入 Allure 报告。",
    handle_alert: "Playwright 下建议在触发弹窗的点击步骤前添加此步骤监听弹窗。",
  };

  const actionOptionsHtml = UI_ACTION_GROUPS.map(
    (g) => `<optgroup label="${escapeHtml(g.group)}">
      ${g.items.map((a) => `<option value="${a.value}" ${action === a.value ? "selected" : ""}>${a.label}</option>`).join("")}
    </optgroup>`
  ).join("");

  const valueInputHtml =
    action === "execute_js"
      ? `<textarea rows="3" placeholder="${valuePlaceholderMap[action]}" oninput="updateStepFieldLive(${idx}, 'value', this.value)" onchange="recordCaseChange()">${escapeHtml(step.value ?? "")}</textarea>`
      : action === "upload_file" && hasNativeFilePicker()
        ? `<div style="display:flex;gap:6px;align-items:center;"><input value="${escapeHtml(step.value ?? "")}" placeholder="${valuePlaceholderMap[action]}" oninput="updateStepFieldLive(${idx}, 'value', this.value)" onchange="recordCaseChange()" /><button class="btn btn-xs btn-outline" onclick="pickUiUploadFile(${idx})">浏览</button></div>`
        : `<input value="${escapeHtml(step.value ?? "")}" placeholder="${valuePlaceholderMap[action] || "支持 {{变量名}}"}" oninput="updateStepFieldLive(${idx}, 'value', this.value)" onchange="recordCaseChange()" />`;

  const valueInlineInFirstRow = showValue && !showLocator;

  return `<div class="step-card step-card-ui ${enabled ? "" : "step-disabled"}">${header}
    <div class="step-body">
      <div class="step-row">
        <div class="step-field step-field-action">
          <label>浏览器动作</label>
          <select onchange="updateUiAction(${idx}, this.value)">
            ${actionOptionsHtml}
          </select>
        </div>
        ${
          showBy
            ? `<div class="step-field step-field-by">
          <label>定位方式</label>
          <select onchange="updateStepField(${idx}, 'by', this.value)">
            ${LOCATOR_TYPES.map((l) => `<option value="${l.value}" ${(step.by || "css") === l.value ? "selected" : ""}>${l.label}</option>`).join("")}
          </select>
        </div>`
            : ""
        }
        ${
          showLocator
            ? `<div class="step-field step-field-grow">
          <label>${locatorLabel}</label>
          <input value="${escapeHtml(step.locator || step.key || "")}" placeholder="${locatorPlaceholder}" oninput="updateStepFieldLive(${idx}, 'locator', this.value)" onchange="recordCaseChange()" />
        </div>`
            : ""
        }
        ${
          valueInlineInFirstRow
            ? `<div class="step-field step-field-grow">
          <label>${valueLabelMap[action] || "参数值"}</label>
          ${valueInputHtml}
        </div>`
            : ""
        }
        ${
          showTimeout
            ? `<div class="step-field step-field-timeout">
          <label>超时(秒)</label>
          <input type="number" min="1" value="${escapeHtml(step.timeout ?? 10)}" oninput="updateStepFieldLive(${idx}, 'timeout', Number(this.value) || 10)" onchange="recordCaseChange()" />
        </div>`
            : ""
        }
      </div>
      ${
        showValue && showLocator
          ? `<div class="step-row">
        <div class="step-field step-field-full">
          <label>${valueLabelMap[action] || "参数值"}</label>
          ${valueInputHtml}
        </div>
      </div>`
          : ""
      }
      ${hintMap[action] ? `<div class="ui-hint">${hintMap[action]}</div>` : ""}
      ${
        sr && (sr.error || (sr.screenshots && sr.screenshots.length))
          ? `<div class="step-result-box" style="margin-top:4px;">
              ${sr.error ? `<div class="ui-hint" style="background:#fef2f2;border-color:#fecaca;color:#991b1b;"><strong>失败原因：</strong>${escapeHtml(sr.error)}</div>` : ""}
              ${(sr.screenshots || []).map((s) => `<img class="step-shot-img" title="${escapeHtml(s.name)}" src="data:image/png;base64,${s.data}" onclick="window.open(this.src, '_blank')" />`).join("")}
            </div>`
          : ""
      }
    </div>
  </div>`;
}
function toggleStepEnabled(idx, checked) {
  currentCase.steps[idx].enabled = checked;
  setCaseDirty(true);
  renderSteps();
  recordCaseChange();
}

function duplicateStep(idx) {
  const clone = JSON.parse(JSON.stringify(currentCase.steps[idx]));
  clone.name = `${clone.name || "步骤"}_副本`;
  currentCase.steps.splice(idx + 1, 0, clone);
  setCaseDirty(true);
  renderSteps();
  recordCaseChange();
}

function updateAssertType(idx, aIdx, val) {
  currentCase.steps[idx].assertions[aIdx].type = val;
  setCaseDirty(true);
  renderSteps();
  recordCaseChange();
}

function updateUiAction(idx, action) {
  currentCase.steps[idx].action = action;
  setCaseDirty(true);
  renderSteps();
  recordCaseChange();
}

function updateStepField(idx, key, val) {
  currentCase.steps[idx][key] = val;
  recordCaseChange();
}

function updateApiReq(idx, key, val) {
  currentCase.steps[idx].request = currentCase.steps[idx].request || {};
  currentCase.steps[idx].request[key] = val;
  recordCaseChange();
}

function updateApiReqJson(idx, key, text) {
  validateAndCommitApiJson(idx, key, text);
}
function updateStepFieldLive(idx, key, val) {
  if (isRestoringCase) return;
  currentCase.steps[idx][key] = val;
  scheduleCaseCommit();
}

function updateApiReqLive(idx, key, val) {
  if (isRestoringCase) return;
  const req = (currentCase.steps[idx].request = currentCase.steps[idx].request || {});
  req[key] = val;
  scheduleCaseCommit();
}

function updateApiReqJsonLive(idx, key, text) {
  if (isRestoringCase) return;
  const req = (currentCase.steps[idx].request = currentCase.steps[idx].request || {});
  const trimmed = text.trim();
  if (!trimmed) {
    delete req[key];
    delete req._json_draft;
    scheduleCaseCommit();
    return;
  }
  try {
    const parsed = JSON.parse(trimmed);
    req[key] = parsed;
    if (text === JSON.stringify(parsed, null, 2)) {
      delete req._json_draft;
    } else {
      req._json_draft = text;
    }
  } catch {
    req._json_draft = text;
  }
  scheduleCaseCommit();
}

function validateAndCommitApiJson(idx, key, text) {
  if (isRestoringCase) return;
  updateApiReqJsonLive(idx, key, text);
  const req = (currentCase.steps[idx].request = currentCase.steps[idx].request || {});
  if (text.trim() && req._json_draft !== undefined) {
    try {
      JSON.parse(text.trim());
    } catch {
      showToast("JSON 格式不正确，请检查引号和括号");
    }
  }
  recordCaseChange();
}

function updateStepRawBodyLive(idx, val) {
  if (isRestoringCase) return;
  const req = (currentCase.steps[idx].request = currentCase.steps[idx].request || {});
  delete req.json;
  delete req._json_draft;
  req.body_type = "raw";
  req.body = val;
  scheduleCaseCommit();
}

function updateStepFormFieldLive(idx, fIdx, field, val) {
  if (isRestoringCase) return;
  const req = (currentCase.steps[idx].request = currentCase.steps[idx].request || {});
  if (Array.isArray(req.form_fields) && req.form_fields[fIdx]) {
    req.form_fields[fIdx][field] = val;
    scheduleCaseCommit();
  }
}

function updateApiKvRowLive(idx, field, rowIdx, part, val) {
  if (isRestoringCase) return;
  const req = (currentCase.steps[idx].request = currentCase.steps[idx].request || {});
  const entries = getApiKvRows(req, field);
  if (!entries[rowIdx]) return;
  if (part === "key") {
    const collision = entries.some(([k], i) => i !== rowIdx && String(k) === String(val));
    if (collision) {
      scheduleCaseCommit();
      return;
    }
    entries[rowIdx][0] = val;
  } else {
    entries[rowIdx][1] = val;
  }
  const rebuilt = {};
  for (const [k, v] of entries) {
    rebuilt[String(k)] = v;
  }
  req[field] = rebuilt;
  scheduleCaseCommit();
}

function updateExtractLive(idx, eIdx, field, val) {
  if (isRestoringCase) return;
  const list = normalizeExtractsForUi(currentCase.steps[idx].extract);
  if (list[eIdx]) {
    list[eIdx][field] = val;
    currentCase.steps[idx].extract = list;
    scheduleCaseCommit();
  }
}

function updateAssertLive(idx, aIdx, field, val) {
  if (isRestoringCase) return;
  const list = currentCase.steps[idx].assertions || [];
  if (list[aIdx]) {
    list[aIdx][field] = val;
    scheduleCaseCommit();
  }
}


function addExtractRow(idx) {
  const list = normalizeExtractsForUi(currentCase.steps[idx].extract);
  list.push({ name: "", path: "" });
  currentCase.steps[idx].extract = list;
  setCaseDirty(true);
  renderSteps();
  recordCaseChange();
}

function updateExtract(idx, eIdx, field, val) {
  const list = normalizeExtractsForUi(currentCase.steps[idx].extract);
  list[eIdx][field] = val;
  currentCase.steps[idx].extract = list;
  recordCaseChange();
}

function removeExtract(idx, eIdx) {
  const list = normalizeExtractsForUi(currentCase.steps[idx].extract);
  list.splice(eIdx, 1);
  currentCase.steps[idx].extract = list;
  setCaseDirty(true);
  renderSteps();
  recordCaseChange();
}

function addAssertRow(idx) {
  currentCase.steps[idx].assertions = currentCase.steps[idx].assertions || [];
  currentCase.steps[idx].assertions.push({ type: "status_code", target: "", expected: 200 });
  setCaseDirty(true);
  renderSteps();
  recordCaseChange();
}

function updateAssert(idx, aIdx, field, val) {
  currentCase.steps[idx].assertions[aIdx][field] = val;
  recordCaseChange();
}

function removeAssert(idx, aIdx) {
  currentCase.steps[idx].assertions.splice(aIdx, 1);
  setCaseDirty(true);
  renderSteps();
  recordCaseChange();
}

function addApiStep() {
  if (!currentCase) return;
  setCaseDirty(true);
  currentCase.steps.push({
    type: "api",
    name: "新建接口步骤",
    request: { method: "GET", url: "{{base_url}}/demo/api/orders", headers: {} },
    extract: [],
    assertions: [{ type: "status_code", target: "", expected: 200 }],
  });
  renderSteps();
  recordCaseChange();
}

function addUiStep() {
  if (!currentCase) return;
  setCaseDirty(true);
  currentCase.steps.push({
    type: "ui",
    name: "新建浏览器步骤",
    action: "open",
    by: "css",
    locator: "",
    value: "{{base_url}}/demo/page",
  });
  renderSteps();
  recordCaseChange();
}

function moveStep(idx, delta) {
  const next = idx + delta;
  if (next < 0 || next >= currentCase.steps.length) return;
  const arr = currentCase.steps;
  [arr[idx], arr[next]] = [arr[next], arr[idx]];
  setCaseDirty(true);
  renderSteps();
  recordCaseChange();
}

function removeStep(idx) {
  currentCase.steps.splice(idx, 1);
  setCaseDirty(true);
  renderSteps();
  recordCaseChange();
}

async function saveCurrentCase() {
  if (!currentCase) return;
  for (let i = 0; i < (currentCase.steps || []).length; i++) {
    const s = currentCase.steps[i];
    if ((s.type || "api").toLowerCase() === "api" && s.request && s.request._json_draft !== undefined) {
      const trimmed = s.request._json_draft.trim();
      if (!trimmed) {
        delete s.request.json;
        delete s.request._json_draft;
      } else {
        try {
          s.request.json = JSON.parse(trimmed);
          delete s.request._json_draft;
        } catch {
          showToast(`第 ${i + 1} 步 Body JSON 格式不正确，请先修正再保存`);
          return;
        }
      }
    }
  }
  recordCaseChange();
  currentCase.name = document.getElementById("case-name").value.trim() || currentCase.filename;
  currentCase.description = document.getElementById("case-desc").value.trim();
  (currentCase.steps || []).forEach((s) => {
    if ((s.type || "api").toLowerCase() === "api" && s.request) {
      ["headers", "params"].forEach((f) => {
        if (s.request[f] && typeof s.request[f] === "object") {
          const clean = {};
          for (const [k, v] of Object.entries(s.request[f])) {
            if (String(k).trim()) clean[String(k).trim()] = v;
          }
          s.request[f] = clean;
        }
      });
    }
  });
  try {
    await apiFetch(`/api/cases/${encodeURIComponent(currentCase.filename)}`, {
      method: "PUT",
      body: JSON.stringify(currentCase),
    });
    setCaseDirty(false);
    caseSavedSnapshot = captureCaseSnapshot();
    caseCurrentSnapshot = caseSavedSnapshot;
    updateCaseHistoryButtons(caseCurrentSnapshot);
    await refreshCasesSidebarOnly();
    showToast("用例已保存");
  } catch (err) {
    showToast("保存用例失败: " + err.message);
  }
}

// ---------- 运行测试与报告 ----------
async function stopRunningTests() {
  try {
    await apiFetch("/api/run/stop", { method: "POST" });
    showToast("已发送停止信号");
  } catch (err) {
    showToast("停止失败: " + err.message);
  }
}

async function executeCases(filenames) {
  if (isTestRunning) {
    showToast("已有测试任务正在运行，请等待完成或先点击停止");
    return;
  }
  isTestRunning = true;
  const banner = document.getElementById("run-result-banner");
  const badge = document.getElementById("run-status-badge");
  const summary = document.getElementById("run-summary-text");
  const logPre = document.getElementById("run-log-pre");
  const allureBtn = document.getElementById("banner-allure-btn");
  const stopBtn = document.getElementById("stop-run-btn");

  banner.classList.remove("hidden");
  badge.className = "badge badge-info";
  badge.textContent = "执行中...";
  summary.textContent = `正在通过 Pytest 执行 ${filenames.length} 条用例，请稍候...`;
  logPre.textContent = "";
  allureBtn.classList.add("hidden");
  stopBtn?.classList.remove("hidden");

  try {
    const res = await apiFetch("/api/run", {
      method: "POST",
      body: JSON.stringify({
        env: document.getElementById("global-env-select").value,
        cases: filenames,
        headless: document.getElementById("global-headless").checked,
        ui_engine: document.getElementById("global-ui-engine").value,
        browser: document.getElementById("global-browser").value,
      }),
    });
    if (res.case_results) {
      Object.assign(caseRunResultsMap, res.case_results);
    }
    if (res.stopped) {
      badge.className = "badge badge-err";
      badge.textContent = "已手动停止";
      summary.textContent = `执行已中断（通过: ${res.passed} | 失败: ${res.failed}）`;
    } else {
      badge.className = `badge ${res.ok ? "badge-ok" : "badge-err"}`;
      badge.textContent = res.ok ? "全部通过" : "存在失败";
      summary.textContent = `通过: ${res.passed} | 失败: ${res.failed}`;
    }
    logPre.textContent = res.log || "";
    if (!res.ok) logPre.classList.remove("hidden");
    if (res.report_url) allureBtn.classList.remove("hidden");
    renderSteps();
    await loadCasesList(currentCase?.filename || null);
  } catch (err) {
    badge.className = "badge badge-err";
    badge.textContent = "执行出错";
    summary.textContent = err.message;
  } finally {
    isTestRunning = false;
    stopBtn?.classList.add("hidden");
  }
}

async function runCurrentCase() {
  if (!currentCase) return;
  await saveCurrentCase();
  await executeCases([currentCase.filename]);
}

async function runSelectedCases() {
  const selected = Array.from(document.querySelectorAll(".case-check:checked")).map((c) => c.value);
  if (!selected.length) {
    showToast("请至少勾选一条用例");
    return;
  }
  await executeCases(selected);
}

function toggleRunLog() {
  document.getElementById("run-log-pre").classList.toggle("hidden");
}

function ensureAllureChineseDefault() {
  try {
    const markerKey = "TESTFLOW_ALLURE_LANG_ZH_V1";
    if (!localStorage.getItem(markerKey)) {
      const raw = localStorage.getItem("ALLURE_REPORT_SETTINGS");
      const settings = raw ? JSON.parse(raw) : {};
      settings.language = "zh";
      localStorage.setItem("ALLURE_REPORT_SETTINGS", JSON.stringify(settings));
      localStorage.setItem(markerKey, "1");
    }
  } catch {
    // ignore storage errors
  }
}

function switchReportKind(kind) {
  activeReportKind = kind;
  document.getElementById("rep-btn-allure")?.classList.toggle("active", kind === "allure");
  document.getElementById("rep-btn-builtin")?.classList.toggle("active", kind === "builtin");
  renderReportFromStatus(latestReportStatus);
}

function getSelectedReportUrl(status) {
  if (!status || !status.exists) return null;
  if (activeReportKind === "builtin") {
    return status.builtin_url || status.allure_url || status.report_url;
  }
  return status.allure_url || status.builtin_url || status.report_url;
}

function renderReportFromStatus(status) {
  const emptyEl = document.getElementById("report-empty");
  const frameEl = document.getElementById("report-iframe");
  const timeEl = document.getElementById("report-updated-at");
  if (!status || !status.exists) {
    emptyEl.classList.remove("hidden");
    frameEl.classList.add("hidden");
    timeEl.textContent = "暂无报告，请先运行一次自动化用例";
    return false;
  }

  if (activeReportKind === "allure" && !status.allure_exists && status.builtin_exists) {
    activeReportKind = "builtin";
    document.getElementById("rep-btn-allure")?.classList.remove("active");
    document.getElementById("rep-btn-builtin")?.classList.add("active");
  }
  const url = getSelectedReportUrl(status);
  emptyEl.classList.add("hidden");
  frameEl.classList.remove("hidden");
  const kindLabel = activeReportKind === "builtin" ? "内置轻量报告" : "Allure 报告";
  timeEl.textContent = `最近生成时间：${status.updated_at} · 当前视图：${kindLabel}`;
  frameEl.src = `${url}?t=${Date.now()}`;
  return true;
}

function openReportInBrowser() {
  const url = getSelectedReportUrl(latestReportStatus) || "/allure-report/index.html";
  window.open(url, "_blank");
}

async function refreshReportFrame() {
  ensureAllureChineseDefault();
  latestReportStatus = await apiFetch("/api/report/status");
  return renderReportFromStatus(latestReportStatus);
}

async function openLatestReport() {
  switchTab("report");
  const ok = await refreshReportFrame();
  if (!ok) {
    showToast("暂无报告，请先运行一次自动化用例");
  }
}

let isWindowMaximized = false;

function applyMaximizedUi(maximized) {
  isWindowMaximized = Boolean(maximized);
  const maxBtn = document.getElementById("win-max-btn");
  if (maxBtn) {
    maxBtn.innerHTML = isWindowMaximized
      ? `<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="3.5" y="1.5" width="7" height="7" rx="1"/><path d="M1.5 4.5v5.5a1 1 0 0 0 1 1h5.5"/></svg>`
      : `<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="8" height="8" rx="1"/></svg>`;
    maxBtn.title = isWindowMaximized ? "还原" : "最大化";
  }
}

window.__onWindowStateChanged = (maximized) => {
  applyMaximizedUi(maximized);
};

function getTopResizeEdge(e) {
  if (isWindowMaximized || e.clientY > 6) return null;
  if (e.clientX <= 8) return "top_left";
  if (e.clientX >= window.innerWidth - 8) return "top_right";
  return "top";
}

function initDesktopWindowControls() {
  const showControls = async () => {
    const el = document.getElementById("window-controls");
    if (el && window.pywebview && window.pywebview.api) {
      el.classList.remove("hidden");
      if (window.pywebview.api.is_maximized) {
        try {
          applyMaximizedUi(await window.pywebview.api.is_maximized());
        } catch {
          // ignore
        }
      }
    }
  };
  showControls();
  window.addEventListener("pywebviewready", showControls);

  let dragStart = null;
  document.querySelectorAll(".brand, .topbar-drag").forEach((el) => {
    el.addEventListener("mousedown", (e) => {
      if (e.button === 0 && !getTopResizeEdge(e) && window.pywebview?.api?.start_drag) {
        dragStart = { x: e.clientX, y: e.clientY };
      } else {
        dragStart = null;
      }
    });
  });

  window.addEventListener("mousemove", (e) => {
    if (dragStart && (e.buttons & 1) === 1) {
      const dx = e.clientX - dragStart.x;
      const dy = e.clientY - dragStart.y;
      if (Math.hypot(dx, dy) >= 3) {
        dragStart = null;
        window.pywebview.api.start_drag();
        return;
      }
    }

    if (!window.pywebview?.api?.start_resize) return;
    const edge = getTopResizeEdge(e);
    if (edge === "top_left") {
      document.body.style.cursor = "nwse-resize";
    } else if (edge === "top_right") {
      document.body.style.cursor = "nesw-resize";
    } else if (edge === "top") {
      document.body.style.cursor = "ns-resize";
    } else if (document.body.style.cursor) {
      document.body.style.cursor = "";
    }
  });

  window.addEventListener("mousedown", (e) => {
    if (e.button !== 0 || !window.pywebview?.api?.start_resize) return;
    const edge = getTopResizeEdge(e);
    if (edge) {
      e.preventDefault();
      dragStart = null;
      window.pywebview.api.start_resize(edge);
    }
  });

  window.addEventListener("mouseup", () => {
    dragStart = null;
  });
}

function winMinimize() {
  if (window.pywebview?.api?.minimize) window.pywebview.api.minimize();
}

async function winToggleMaximize() {
  if (window.pywebview?.api?.toggle_maximize) {
    const state = await window.pywebview.api.toggle_maximize();
    applyMaximizedUi(state);
  }
}

function winClose() {
  if ((caseDirty || envDirty) && !confirm("当前还有未保存的修改，确定直接关闭吗？")) {
    return;
  }
  if (window.pywebview?.api?.close) window.pywebview.api.close();
}

function initDirtyAndShortcuts() {
  ["case-name", "case-desc"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("input", () => {
      setCaseDirty(true);
      scheduleCaseCommit();
    });
    el.addEventListener("change", () => recordCaseChange());
    el.addEventListener("blur", () => recordCaseChange());
  });

  window.addEventListener("keydown", async (e) => {
    if (e.key === "F1") {
      e.preventDefault();
      document.getElementById("shortcuts-modal")?.classList.toggle("hidden");
      return;
    }
    const mod = e.ctrlKey || e.metaKey;
    if (!mod) return;
    const key = e.key.toLowerCase();

    if (key === "s") {
      e.preventDefault();
      if (document.getElementById("tab-cases")?.classList.contains("active")) {
        await saveCurrentCase();
      } else if (document.getElementById("tab-envs")?.classList.contains("active")) {
        await saveEnvs();
      }
      return;
    }

    if (e.key === "Enter") {
      e.preventDefault();
      if (document.getElementById("tab-debug")?.classList.contains("active")) {
        await sendDebugRequest();
      } else if (document.getElementById("tab-cases")?.classList.contains("active")) {
        await runCurrentCase();
      }
      return;
    }

    if (key === "f") {
      e.preventDefault();
      switchTab("cases");
      const searchEl = document.getElementById("case-search");
      if (searchEl) {
        searchEl.focus();
        searchEl.select();
      }
      return;
    }

    if (key === "n" && !isTextInputFocused()) {
      e.preventDefault();
      switchTab("cases");
      await createNewCase();
      return;
    }

    const tabMap = { "1": "debug", "2": "cases", "3": "envs", "4": "report" };
    if (tabMap[e.key]) {
      e.preventDefault();
      if (tabMap[e.key] === "report") {
        await openLatestReport();
      } else {
        switchTab(tabMap[e.key]);
      }
      return;
    }

    if (!hasOpenModal()) {
      const inCases = document.getElementById("tab-cases")?.classList.contains("active");
      const inEnvs = document.getElementById("tab-envs")?.classList.contains("active");
      const inCaseSearch = document.activeElement?.id === "case-search";
      if (key === "z" && !e.shiftKey) {
        if (inCases && !inCaseSearch) {
          e.preventDefault();
          undoCase();
          return;
        }
        if (inEnvs) {
          e.preventDefault();
          undoEnv();
          return;
        }
      }
      if (key === "y" || (key === "z" && e.shiftKey)) {
        if (inCases && !inCaseSearch) {
          e.preventDefault();
          redoCase();
          return;
        }
        if (inEnvs) {
          e.preventDefault();
          redoEnv();
          return;
        }
      }
    }
  });
}

function initModalShortcuts() {
  document.querySelectorAll(".modal").forEach((modal) => {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.classList.add("hidden");
    });
  });
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal").forEach((m) => m.classList.add("hidden"));
    }
  });
}

function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem("TESTFLOW_PREFS") || "{}");
  } catch {
    return {};
  }
}

function savePrefs() {
  try {
    localStorage.setItem(
      "TESTFLOW_PREFS",
      JSON.stringify({
        env: document.getElementById("global-env-select")?.value || "local_demo",
        ui_engine: document.getElementById("global-ui-engine")?.value || "selenium",
        browser: document.getElementById("global-browser")?.value || "auto",
        headless: document.getElementById("global-headless")?.checked ?? true,
        dbg_timeout: Number(document.getElementById("dbg-timeout")?.value) || 30,
      })
    );
  } catch {
    // ignore
  }
}

function initPrefsPersistence() {
  const prefs = loadPrefs();
  if (prefs.ui_engine) document.getElementById("global-ui-engine").value = prefs.ui_engine;
  if (prefs.browser) document.getElementById("global-browser").value = prefs.browser;
  if (typeof prefs.headless === "boolean") document.getElementById("global-headless").checked = prefs.headless;
  if (prefs.dbg_timeout && document.getElementById("dbg-timeout")) {
    document.getElementById("dbg-timeout").value = prefs.dbg_timeout;
  }
  ["global-env-select", "global-ui-engine", "global-browser", "global-headless", "dbg-timeout"].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", savePrefs);
  });
}

window.addEventListener("beforeunload", (e) => {
  if (caseDirty || envDirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});

// 初始化
(async function init() {
  initDesktopWindowControls();
  initDirtyAndShortcuts();
  initModalShortcuts();
  initPrefsPersistence();
  await loadEnvs();
  await loadCasesList();
})();
