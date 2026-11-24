(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = {
    algorithms: [],
    algorithmMap: {},
    jobs: [],
    ai: null,
    health: null,
    tab: "nl",
    filter: "all",
    jobsSignature: "",
    pollTimer: null,
    busy: false,
    videoJob: null,
  };

  const STATUS_LABEL = {
    pending: "排队中",
    parsing: "解析中",
    executing: "执行算法",
    rendering: "渲染动画",
    synthesizing: "合成音视频",
    validating: "质量检查",
    completed: "已完成",
    failed: "失败",
  };
  const ACTIVE = new Set(["pending", "parsing", "executing", "rendering", "synthesizing", "validating"]);

  // ---------------------------------------------------------------- utilities
  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const data = await response.json();
        if (typeof data.detail === "string") detail = data.detail;
        else if (Array.isArray(data.detail)) detail = data.detail.map((d) => d.msg || JSON.stringify(d)).join("；");
      } catch (_) {
        /* ignore */
      }
      throw new Error(detail);
    }
    return response.status === 204 ? null : response.json();
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));
  }

  function fmtTime(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  function toast(message, kind = "") {
    const node = $("toast");
    node.textContent = message;
    node.className = `toast show ${kind}`.trim();
    clearTimeout(node._timer);
    node._timer = setTimeout(() => {
      node.className = "toast";
    }, 4200);
  }

  function setHint(text, kind = "") {
    const node = $("formHint");
    node.textContent = text || "";
    node.className = `submit-hint ${kind}`.trim();
  }

  // ---------------------------------------------------------------- AI status
  function aiLabel() {
    const ai = state.ai;
    if (!ai) return { cls: "warn", text: "大模型状态未知" };
    if (!ai.has_key) return { cls: "warn", text: "本地模板 · 未配置 Key" };
    if (!ai.enabled) return { cls: "warn", text: "AI 已关闭" };
    if (ai.last_error) return { cls: "bad", text: "AI 调用异常" };
    return { cls: "ok", text: `DeepSeek · ${ai.model}` };
  }

  function renderAI() {
    const ai = state.ai;
    const label = aiLabel();
    const pill = $("aiPill");
    pill.className = `pill ${label.cls}`;
    $("aiPillText").textContent = label.text;
    pill.title = ai ? `模型 ${ai.model} · 模式 ${ai.mode} · ${ai.env_file}` : "大模型状态";

    const banner = $("aiBanner");
    let message = "";
    if (!ai) {
      message = "正在读取大模型配置…";
    } else if (!ai.has_key) {
      message = "当前使用本地模板讲解：未检测到 DEEPSEEK_API_KEY。算法、动画和视频与调用大模型时一致，但讲解文案不会经过模型润色。";
    } else if (!ai.enabled) {
      message = `已配置 Key，但 AI 模式为 ${ai.mode}（关闭状态）。需要调用大模型时请在「AI 设置」中改为 auto 或 on。`;
    } else if (ai.last_error) {
      message = `最近一次大模型调用失败，已自动回退本地模板：${ai.last_error}`;
    }
    if (message) {
      banner.classList.remove("hidden");
      banner.innerHTML = `<span>${esc(message)}</span><button class="btn ghost" type="button" id="bannerAiBtn">配置 / 检查</button>`;
      $("bannerAiBtn").onclick = openAIDialog;
    } else {
      banner.classList.add("hidden");
      banner.innerHTML = "";
    }
    renderAIDialogState();
  }

  async function loadAI() {
    try {
      state.ai = await api("/api/v1/settings/ai");
    } catch (error) {
      state.ai = null;
      console.warn(error);
    }
    renderAI();
  }

  function renderAIDialogState() {
    const node = $("aiDialogState");
    const ai = state.ai;
    if (!node) return;
    if (!ai) {
      node.innerHTML = "<strong>无法读取 AI 配置</strong>";
      return;
    }
    const keyText = ai.has_key ? `已配置（${esc(ai.masked_key)}）` : "未配置";
    let test = "";
    if (ai.last_test) {
      test = ai.last_test.ok
        ? `<span style="color:var(--green)">上次测试成功 · ${ai.last_test.latency_ms}ms</span>`
        : `<span style="color:var(--red)">上次测试失败 · ${esc(ai.last_test.error || "未知错误")}</span>`;
    }
    node.innerHTML = `
      <strong>${ai.enabled ? "DeepSeek 已启用" : "当前使用本地模板"}</strong>
      <span>API Key：${keyText} · 模型：${esc(ai.model)}</span>
      <span>模式：${esc(ai.mode)} · 配置文件：${esc(ai.env_file)}</span>
      ${test}
    `;
    $("envFileLabel").textContent = ai.env_file || ".env";
  }

  async function openAIDialog() {
    try {
      await loadAI();
    } catch (_) {
      /* ignore */
    }
    const ai = state.ai || {};
    $("aiKey").value = "";
    $("aiKey").placeholder = ai.has_key
      ? `已配置 ${ai.masked_key}（留空不修改）`
      : "sk-...（DeepSeek API Key）";
    $("aiModel").value = ai.model || "deepseek-chat";
    $("aiBaseUrl").value = ai.base_url || "https://api.deepseek.com";
    $("aiMode").value = ai.mode || "auto";
    $("clearKey").checked = false;
    $("aiKey").disabled = false;
    $("aiTestResult").className = "test-result hidden";
    $("aiTestResult").textContent = "";
    $("aiDialog").showModal();
  }

  async function saveAISettings() {
    const key = $("aiKey").value.trim();
    const body = {
      api_key: key || null,
      model: $("aiModel").value.trim() || null,
      base_url: $("aiBaseUrl").value.trim() || null,
      mode: $("aiMode").value,
      clear_key: $("clearKey").checked,
    };
    const button = $("saveAiBtn");
    button.disabled = true;
    button.textContent = "保存中…";
    try {
      await api("/api/v1/settings/ai", { method: "POST", body: JSON.stringify(body) });
      $("aiKey").value = "";
      await loadAI();
      toast("AI 配置已保存并生效", "ok");
    } catch (error) {
      toast(`保存失败：${error.message}`, "error");
    } finally {
      button.disabled = false;
      button.textContent = "保存设置";
    }
  }

  async function testAIConnection() {
    const button = $("testAiBtn");
    const box = $("aiTestResult");
    button.disabled = true;
    button.textContent = "测试中…";
    box.className = "test-result";
    box.textContent = "正在请求 DeepSeek…";
    try {
      const result = await api("/api/v1/ai/test", { method: "POST", body: "{}" });
      if (result.ok) {
        box.className = "test-result ok";
        box.textContent = `连接成功\n模型：${result.model}\n延迟：${result.latency_ms}ms\n返回：${JSON.stringify(result.response)}`;
        toast("DeepSeek 连接成功", "ok");
      } else {
        box.className = "test-result bad";
        box.textContent = `连接失败\n${result.error || "未知错误"}${result.hint ? `\n提示：${result.hint}` : ""}`;
        toast("DeepSeek 连接失败", "error");
      }
      await loadAI();
    } catch (error) {
      box.className = "test-result bad";
      box.textContent = `请求失败：${error.message}`;
    } finally {
      button.disabled = false;
      button.textContent = "测试连接";
    }
  }

  // ---------------------------------------------------------------- algorithms / params
  async function loadAlgorithms() {
    const data = await api("/api/v1/algorithms");
    state.algorithms = data;
    state.algorithmMap = Object.fromEntries(data.map((item) => [item.key, item]));
    const select = $("algorithmSelect");
    select.innerHTML = data
      .map((item) => `<option value="${esc(item.key)}">${esc(item.title)} · ${esc(item.category)}</option>`)
      .join("");
    renderParamFields();
  }

  function renderParamFields() {
    const keyName = $("algorithmSelect").value || (state.algorithms[0] || {}).key;
    const spec = state.algorithmMap[keyName];
    const container = $("paramFields");
    if (!spec) {
      container.innerHTML = "";
      return;
    }
    const defaults = spec.defaults || {};
    const rows = Object.entries(defaults).map(([key, value]) => {
      const id = `param-${key}`;
      let control;
      if (key === "edges" || key === "positions" || (Array.isArray(value) && value.length && Array.isArray(value[0]))) {
        control = `<textarea id="${id}" rows="3" spellcheck="false">${esc(JSON.stringify(value))}</textarea>`;
      } else if (Array.isArray(value)) {
        control = `<input id="${id}" type="text" value="${esc(value.join(", "))}">`;
      } else if (typeof value === "number") {
        control = `<input id="${id}" type="number" step="1" value="${esc(value)}">`;
      } else {
        control = `<input id="${id}" type="text" value="${esc(value)}">`;
      }
      const hint = key === "edges" ? "JSON 二维数组" : key === "array" || key === "values" ? "逗号分隔" : "";
      return `<label class="field"><span>${esc(key)} ${hint ? `<em style="font-style:normal;color:var(--muted-2)">（${hint}）</em>` : ""}</span>${control}</label>`;
    });
    container.innerHTML = rows.join("");
  }

  function buildParams() {
    const spec = state.algorithmMap[$("algorithmSelect").value];
    if (!spec) throw new Error("请选择算法");
    const params = {};
    for (const [key, fallback] of Object.entries(spec.defaults || {})) {
      const input = $(`param-${key}`);
      if (!input) continue;
      const raw = input.value.trim();
      if (raw === "") continue;
      if (key === "edges" || key === "positions" || (Array.isArray(fallback) && fallback.length && Array.isArray(fallback[0]))) {
        try {
          params[key] = JSON.parse(raw);
        } catch (_) {
          throw new Error(`${key} 不是合法 JSON，请检查格式`);
        }
      } else if (Array.isArray(fallback)) {
        const parts = raw.split(/[,，;；\s]+/).filter(Boolean);
        params[key] = parts.map((part) => {
          const number = Number(part);
          return Number.isFinite(number) && part.trim() !== "" ? number : part;
        });
      } else if (typeof fallback === "number") {
        const number = Number(raw);
        if (!Number.isFinite(number)) throw new Error(`${key} 必须是数字`);
        params[key] = number;
      } else {
        params[key] = raw;
      }
    }
    return params;
  }

  // ---------------------------------------------------------------- create task
  function renderTabs() {
    document.querySelectorAll(".tab").forEach((button) => {
      button.classList.toggle("active", button.dataset.tab === state.tab);
    });
    $("pane-nl").classList.toggle("hidden", state.tab !== "nl");
    $("pane-param").classList.toggle("hidden", state.tab !== "param");
  }

  function optionsPayload() {
    return {
      render_quality: $("quality").value,
      tts: $("tts").checked,
      voice: $("voice").value,
      theme: $("theme").value,
      steps_per_segment: Math.max(1, Math.min(8, Number($("steps").value) || 3)),
    };
  }

  async function submitCreate(event) {
    event.preventDefault();
    const button = $("submitBtn");
    if (button.disabled) return;
    setHint("");
    let body;
    try {
      if (state.tab === "nl") {
        const prompt = $("prompt").value.trim();
        if (!prompt) throw new Error("请先输入自然语言描述");
        body = { prompt, options: optionsPayload() };
      } else {
        const algorithm = $("algorithmSelect").value;
        if (!algorithm) throw new Error("请选择算法");
        body = { algorithm, params: buildParams(), options: optionsPayload() };
      }
      const title = $("titleInput").value.trim();
      if (title) body.title = title;
    } catch (error) {
      setHint(error.message, "error");
      return;
    }
    button.disabled = true;
    button.textContent = "提交中…";
    try {
      const result = await api("/api/v1/generate", { method: "POST", body: JSON.stringify(body) });
      setHint(`已提交任务 ${result.job.id}，正在后台生成…`, "ok");
      toast("任务已提交");
      await refreshJobs(true);
      if (result.job.id) {
        setTimeout(() => {
          const card = document.querySelector(`[data-job-id="${CSS.escape(result.job.id)}"]`);
          if (card) card.scrollIntoView({ behavior: "smooth", block: "center" });
        }, 200);
      }
    } catch (error) {
      setHint(`提交失败：${error.message}`, "error");
      toast(`提交失败：${error.message}`, "error");
    } finally {
      button.disabled = false;
      button.textContent = "生成视频";
    }
  }

  // ---------------------------------------------------------------- jobs
  function jobMatchesFilter(job) {
    if (state.filter === "all") return true;
    if (state.filter === "active") return ACTIVE.has(job.status);
    return job.status === state.filter;
  }

  function aiBadge(job) {
    if (ACTIVE.has(job.status) && !job.ai_status) {
      return `<span class="badge">AI 判定中</span>`;
    }
    switch (job.ai_status) {
      case "used":
        return `<span class="badge ai-used">✦ DeepSeek 已调用${job.ai_calls ? ` · ${job.ai_calls} 次` : ""}</span>`;
      case "failed":
        return `<span class="badge ai-failed">AI 调用失败 · 本地模板</span>`;
      case "disabled":
        return `<span class="badge ai-local">本地模板（生成时未启用 AI）</span>`;
      case "unused":
        return `<span class="badge">AI 未触发</span>`;
      default:
        return `<span class="badge">AI 状态未知</span>`;
    }
  }

  function jobCard(job) {
    const running = ACTIVE.has(job.status);
    const statusClass = `st-${job.status}`;
    const progress = Math.round((job.progress || 0) * 100);
    const title = job.title || job.algorithm || "未命名任务";
    const meta = [
      job.algorithm || "AI 解析",
      job.id,
      fmtTime(job.created_at),
    ].filter(Boolean).join(" · ");
    const actions = [];
    if (job.status === "completed") {
      actions.push(`<button class="btn ghost" type="button" data-action="play">预览</button>`);
      actions.push(`<a class="btn ghost" href="/api/v1/jobs/${encodeURIComponent(job.id)}/subtitles" target="_blank" rel="noreferrer">字幕 SRT</a>`);
      actions.push(`<a class="btn ghost" href="/api/v1/jobs/${encodeURIComponent(job.id)}/events" target="_blank" rel="noreferrer">事件 JSON</a>`);
    }
    if (job.status === "failed") {
      actions.push(`<button class="btn ghost" type="button" data-action="retry">重试</button>`);
    }
    if (running || job.status === "failed") {
      actions.push(`<button class="btn ghost" type="button" data-action="detail">${job.status === "failed" ? "错误" : "详情"}</button>`);
    }
    const badges = [
      aiBadge(job),
      job.verified ? `<span class="badge ok">✓ 算法校验</span>` : "",
      job.duration ? `<span class="badge">${job.duration.toFixed(1)}s</span>` : "",
    ].join("");
    const error = job.status === "failed" && job.error
      ? `<pre class="job-error" data-error hidden>${esc(job.error)}</pre>`
      : "";
    return `
      <article class="job ${running ? "running" : ""} ${job.status === "failed" ? "failed" : ""}" data-job-id="${esc(job.id)}">
        <div class="job-top">
          <div>
            <h3 class="job-title">${esc(title)}</h3>
            <p class="job-meta">${esc(meta)}</p>
          </div>
          <span class="status ${statusClass}">${esc(STATUS_LABEL[job.status] || job.status)}</span>
        </div>
        <div class="progress"><div style="width:${progress}%"></div></div>
        <div class="job-badges">${badges}</div>
        <div class="stage">${esc(job.stage || "")}</div>
        ${error}
        ${actions.length ? `<div class="job-actions">${actions.join("")}</div>` : ""}
      </article>
    `;
  }

  function renderJobs() {
    const list = $("jobList");
    const jobs = [...state.jobs].reverse().filter(jobMatchesFilter);
    $("jobCount").textContent = `${state.jobs.length} 个任务`;
    if (!jobs.length) {
      list.innerHTML = `<div class="empty">${state.jobs.length ? "当前筛选下没有任务" : "还没有任务，先在左侧创建一个视频吧"}</div>`;
      return;
    }
    list.innerHTML = jobs.map(jobCard).join("");
    list.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", () => handleJobAction(button));
    });
  }

  async function refreshJobs(force = false) {
    try {
      const jobs = await api("/api/v1/jobs?limit=100");
      const signature = JSON.stringify(jobs);
      if (force || signature !== state.jobsSignature) {
        state.jobs = jobs;
        state.jobsSignature = signature;
        renderJobs();
      }
    } catch (error) {
      $("jobList").innerHTML = `<div class="empty">任务列表加载失败：${esc(error.message)}</div>`;
    }
    schedulePolling();
  }

  function schedulePolling() {
    clearTimeout(state.pollTimer);
    const active = state.jobs.some((job) => ACTIVE.has(job.status));
    state.pollTimer = setTimeout(() => refreshJobs(), active ? 1600 : 5000);
  }

  function handleJobAction(button) {
    const card = button.closest("[data-job-id]");
    if (!card) return;
    const job = state.jobs.find((item) => item.id === card.dataset.jobId);
    if (!job) return;
    const action = button.dataset.action;
    if (action === "play") openVideo(job);
    if (action === "detail") {
      const pre = card.querySelector("[data-error]");
      if (pre) pre.hidden = !pre.hidden;
    }
    if (action === "retry") retryJob(job);
  }

  async function retryJob(job) {
    try {
      const result = await api(`/api/v1/jobs/${encodeURIComponent(job.id)}/retry`, { method: "POST", body: "{}" });
      toast(`已重新提交：${result.job.id}`, "ok");
      await refreshJobs(true);
    } catch (error) {
      toast(`重试失败：${error.message}`, "error");
    }
  }

  function openVideo(job) {
    state.videoJob = job;
    $("videoTitle").textContent = job.title || "视频预览";
    const video = $("videoPlayer");
    video.pause();
    video.src = `/api/v1/jobs/${encodeURIComponent(job.id)}/video`;
    video.load();
    const links = [
      `<a href="/api/v1/jobs/${encodeURIComponent(job.id)}/video" download>下载 MP4</a>`,
      `<a href="/api/v1/jobs/${encodeURIComponent(job.id)}/subtitles" target="_blank" rel="noreferrer">字幕 SRT</a>`,
      `<a href="/api/v1/jobs/${encodeURIComponent(job.id)}/events" target="_blank" rel="noreferrer">动画事件 JSON</a>`,
    ];
    $("videoLinks").innerHTML = links.join("");
    $("videoDialog").showModal();
  }

  // ---------------------------------------------------------------- batch
  async function submitBatch() {
    const raw = $("batchJson").value.trim();
    if (!raw) {
      toast("请先粘贴批量任务 JSON", "error");
      return;
    }
    let data;
    try {
      data = JSON.parse(raw);
    } catch (error) {
      toast(`JSON 解析失败：${error.message}`, "error");
      return;
    }
    let tasks = Array.isArray(data) ? data : data.tasks;
    if (!Array.isArray(tasks) || !tasks.length) {
      toast("批量任务需要 tasks 数组", "error");
      return;
    }
    const defaults = (!Array.isArray(data) && data.defaults) || {};
    tasks = tasks.map((task) => {
      if (typeof task === "string") return { prompt: task, options: defaults };
      const normalized = { ...task, options: { ...defaults, ...(task.options || {}) } };
      if (normalized.id && !normalized.task_id) normalized.task_id = normalized.id;
      delete normalized.id;
      return normalized;
    });
    const button = $("batchBtn");
    button.disabled = true;
    try {
      const result = await api("/api/v1/batch", {
        method: "POST",
        body: JSON.stringify({ tasks, batch_name: Array.isArray(data) ? null : data.batch_name }),
      });
      toast(`批次 ${result.batch_id} 已提交（${result.jobs.length} 个任务）`, "ok");
      $("batchJson").value = "";
      await refreshJobs(true);
    } catch (error) {
      toast(`批次提交失败：${error.message}`, "error");
    } finally {
      button.disabled = false;
    }
  }

  // ---------------------------------------------------------------- health
  async function loadHealth() {
    try {
      state.health = await api("/health");
      $("serverDot").className = "server-dot ok";
    } catch (_) {
      $("serverDot").className = "server-dot bad";
    }
  }

  // ---------------------------------------------------------------- events
  function bindEvents() {
    document.querySelectorAll(".tab").forEach((button) => {
      button.addEventListener("click", () => {
        state.tab = button.dataset.tab;
        renderTabs();
      });
    });
    document.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        $("prompt").value = chip.dataset.prompt || "";
        $("prompt").focus();
      });
    });
    document.querySelectorAll(".filter").forEach((button) => {
      button.addEventListener("click", () => {
        state.filter = button.dataset.filter;
        document.querySelectorAll(".filter").forEach((item) => item.classList.toggle("active", item === button));
        renderJobs();
      });
    });
    $("algorithmSelect").addEventListener("change", renderParamFields);
    $("createForm").addEventListener("submit", submitCreate);
    $("refreshBtn").addEventListener("click", () => refreshJobs(true));
    $("aiSettingsBtn").addEventListener("click", openAIDialog);
    $("aiPill").addEventListener("click", openAIDialog);
    $("saveAiBtn").addEventListener("click", saveAISettings);
    $("testAiBtn").addEventListener("click", testAIConnection);
    $("closeAiBtn").addEventListener("click", () => $("aiDialog").close());
    $("closeVideoBtn").addEventListener("click", () => {
      $("videoPlayer").pause();
      $("videoPlayer").removeAttribute("src");
      $("videoPlayer").load();
      $("videoDialog").close();
    });
    $("videoDialog").addEventListener("close", () => {
      $("videoPlayer").pause();
      $("videoPlayer").removeAttribute("src");
      $("videoPlayer").load();
    });
    $("clearKey").addEventListener("change", () => {
      $("aiKey").disabled = $("clearKey").checked;
      if ($("clearKey").checked) $("aiKey").value = "";
    });
    $("batchBtn").addEventListener("click", submitBatch);
    $("batchFile").addEventListener("change", async (event) => {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      try {
        $("batchJson").value = await file.text();
        toast(`已读取 ${file.name}`, "ok");
      } catch (error) {
        toast(`读取文件失败：${error.message}`, "error");
      }
    });
    $("tts").addEventListener("change", () => {
      $("voice").disabled = !$("tts").checked;
    });
  }

  // ---------------------------------------------------------------- boot
  async function init() {
    bindEvents();
    if (location.hash === "#param") state.tab = "param";
    renderTabs();
    try {
      await loadAlgorithms();
    } catch (error) {
      toast(`算法列表加载失败：${error.message}`, "error");
    }
    await loadHealth();
    await loadAI();
    await refreshJobs(true);
    setInterval(loadHealth, 30000);
    setInterval(loadAI, 30000);
    if (location.hash === "#ai") {
      setTimeout(openAIDialog, 400);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
