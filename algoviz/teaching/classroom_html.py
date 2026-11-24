"""生成 M3-8 课堂播放器：完全离线、组件化、多 CaseRun。

HTML 只是另一个渲染器：它消费同一份 ClassroomDeck（AnimationTrace + VisualPlan +
StepHint），不重新执行算法，也不根据视觉状态反推算法语义。
"""
from __future__ import annotations

import json
from pathlib import Path

from .classroom import ClassroomDeck


def _json_for_html(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def write_classroom_html(deck: ClassroomDeck, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    html = TEMPLATE.replace("__DATA__", _json_for_html(deck.model_dump(mode="json")))
    path.write_text(html, encoding="utf-8")
    return path


TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Two Sum · 算法课堂演示台</title>
<style>
:root{
  --bg:#09111f;--bg2:#0d1829;--panel:#15243d;--panel2:#1b3050;--panel3:#102039;
  --border:#29415f;--border2:#355275;--text:#edf4ff;--muted:#9aabc4;--dim:#6f829e;
  --accent:#fbbf24;--accent2:#f59e0b;--blue:#38bdf8;--green:#34d399;--red:#fb7185;
  --code:#0a1424;--shadow:0 18px 50px rgba(0,0,0,.34);
}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:
  radial-gradient(1200px 700px at 18% -10%,rgba(56,189,248,.10),transparent 62%),
  radial-gradient(900px 600px at 98% 0%,rgba(251,191,36,.08),transparent 58%),
  var(--bg);color:var(--text);
  font-family:"Microsoft YaHei","PingFang SC","Noto Sans CJK SC",sans-serif}
button,select,input{font-family:inherit}
[hidden]{display:none!important}
.page{max-width:1720px;margin:0 auto;padding:18px 22px 118px}
.panel{background:linear-gradient(180deg,rgba(27,48,80,.86),rgba(21,36,61,.92));
  border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow)}
.topbar{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;
  padding:18px 22px;margin-bottom:14px;position:relative;overflow:hidden}
.topbar:before{content:"";position:absolute;inset:0 auto 0 0;width:5px;
  background:linear-gradient(180deg,var(--accent),var(--blue))}
.kicker{font-size:11px;letter-spacing:.2em;color:var(--accent);font-weight:800;text-transform:uppercase}
h1{font-size:25px;line-height:1.2;margin:7px 0 5px;letter-spacing:.2px}
.sub{font-size:13px;color:var(--muted)}
.current-case{min-width:330px;max-width:500px;padding:11px 14px;border:1px solid var(--border);
  border-radius:13px;background:rgba(9,17,31,.36)}
.current-case .name{font-size:16px;font-weight:800;margin-bottom:4px}
.current-case .input-line{font-size:12px;color:var(--muted);line-height:1.6;word-break:break-word}
.badges{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}
.badge{display:inline-flex;align-items:center;border:1px solid var(--border2);background:rgba(16,32,57,.7);
  color:var(--muted);border-radius:999px;padding:3px 9px;font-size:11px;font-weight:700;white-space:nowrap}
.badge.ok{color:var(--green);border-color:rgba(52,211,153,.55);background:rgba(52,211,153,.08)}
.badge.warn{color:var(--accent);border-color:rgba(251,191,36,.5);background:rgba(251,191,36,.08)}
.badge.bad{color:var(--red);border-color:rgba(251,113,133,.5);background:rgba(251,113,133,.08)}
.badge.blue{color:var(--blue);border-color:rgba(56,189,248,.55);background:rgba(56,189,248,.08)}
.workspace{display:grid;grid-template-columns:minmax(0,1fr) 390px;gap:14px;align-items:start}
.stage{min-width:0;display:grid;gap:14px}
.component-layout{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1fr) minmax(300px,1.25fr);
  gap:14px;align-items:start}
.component{min-width:0;padding:14px;position:relative}
.component[data-slot="array"]{grid-column:1/-1}
.component[data-slot="code"]{grid-column:3;grid-row:2 / span 2}
.panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px}
.panel-head h2{font-size:14px;color:var(--text);margin:0;letter-spacing:.04em}
.panel-head .hint{font-size:11px;color:var(--muted)}
.array-wrap{display:flex;align-items:center;justify-content:center;gap:18px;min-height:112px;
  flex-wrap:wrap;padding:10px 6px 2px}
.array-cells{display:flex;align-items:flex-start;justify-content:center;gap:10px;flex-wrap:wrap}
.cell{position:relative;width:74px;height:74px;border:2px solid var(--border2);border-radius:14px;
  background:linear-gradient(180deg,rgba(27,48,80,.96),rgba(16,32,57,.96));
  display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:800;
  transition:border-color .16s ease,background .16s ease,transform .16s ease,color .16s ease}
.cell .idx{position:absolute;bottom:-24px;color:var(--dim);font-size:11px;font-weight:600}
.cell .pt{position:absolute;top:-22px;left:50%;transform:translateX(-50%);color:var(--accent);
  font-size:11px;font-weight:800;white-space:nowrap;background:rgba(9,17,31,.72);
  border:1px solid rgba(251,191,36,.35);border-radius:999px;padding:1px 6px}
.cell.active{border-color:var(--accent);background:rgba(251,191,36,.14);color:#fff;
  box-shadow:0 0 0 4px rgba(251,191,36,.08)}
.cell.found{border-color:var(--green);background:rgba(52,211,153,.14);color:#eafff7}
.cell.found .idx{color:var(--green)}
.array-target{color:var(--accent);font-size:14px;font-weight:800;white-space:nowrap;
  background:rgba(251,191,36,.08);border:1px solid rgba(251,191,36,.35);border-radius:999px;padding:7px 12px}
.empty{color:var(--muted);font-size:12px;padding:10px 4px;line-height:1.6}
.table-wrap{overflow:auto;max-height:250px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 7px;border-bottom:1px solid rgba(42,65,95,.7)}
th{color:var(--muted);font-size:11px;font-weight:700}
tr.hit td{color:var(--accent);background:rgba(251,191,36,.07)}
tr.fresh td{background:rgba(56,189,248,.08);color:#dff6ff}
.lookup{display:flex;align-items:center;gap:8px;min-height:28px;margin-top:8px;color:var(--muted);font-size:12px}
.pill{border-radius:999px;padding:3px 9px;font-size:10px;font-weight:800;letter-spacing:.08em}
.pill.hit{color:var(--green);border:1px solid var(--green);background:rgba(52,211,153,.1)}
.pill.miss{color:var(--red);border:1px solid var(--red);background:rgba(251,113,133,.08)}
.pill.none{color:var(--muted);border:1px solid var(--border)}
.vars{display:grid;gap:7px}
.var{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:7px 9px;
  border:1px solid rgba(42,65,95,.8);border-radius:9px;background:rgba(16,32,57,.6)}
.var .label{color:var(--muted);font-size:12px;flex:none}
.var .value{font-size:14px;font-weight:700;word-break:break-all;text-align:right;color:var(--text)}
.var.changed{border-color:rgba(251,191,36,.5);background:rgba(251,191,36,.07)}
.var.changed .value{color:var(--accent)}
.code-scroll{max-height:360px;overflow:auto;background:var(--code);border:1px solid rgba(42,65,95,.8);
  border-radius:10px;padding:8px 7px;font-family:"Cascadia Mono",Consolas,"SFMono-Regular",monospace;
  font-size:12.5px;line-height:1.55}
.code-line{display:flex;gap:10px;padding:2px 6px;border-radius:6px;white-space:pre;color:#cfe0f6}
.code-line .no{width:22px;flex:none;text-align:right;color:#526b8b;user-select:none}
.code-line.active{background:rgba(251,191,36,.14);box-shadow:inset 3px 0 0 var(--accent);color:#fff}
.step-panel{padding:14px 16px}
.step-top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:7px}
.step-top h2{font-size:15px;margin:0}
.step-desc{font-size:13px;line-height:1.7;color:var(--muted);min-height:24px}
.step-meta{font-size:11px;line-height:1.7;color:var(--dim);margin-top:5px}
.teaching{display:grid;gap:14px}
.teaching .panel{padding:14px}
.case-panel .case-list{display:grid;gap:7px;max-height:286px;overflow:auto;padding-right:2px}
.case-card{width:100%;text-align:left;border:1px solid var(--border);background:rgba(16,32,57,.6);
  color:var(--text);border-radius:10px;padding:9px 10px;cursor:pointer;transition:.15s ease}
.case-card:hover{border-color:var(--blue)}
.case-card.active{border-color:var(--accent);background:rgba(251,191,36,.08);
  box-shadow:inset 3px 0 0 var(--accent)}
.case-card .row{display:flex;justify-content:space-between;align-items:center;gap:8px}
.case-card .name{font-size:13px;font-weight:800}
.case-card .input{font-size:11px;color:var(--muted);margin-top:3px;line-height:1.5;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.case-error{margin-top:9px;padding:9px;border:1px solid rgba(251,113,133,.4);
  background:rgba(251,113,133,.06);border-radius:9px;color:#ffc4cd;font-size:12px;line-height:1.6}
.eyebrow{font-size:10px;letter-spacing:.18em;font-weight:800;color:var(--accent);text-transform:uppercase}
.hint-panel h2{font-size:16px;margin:6px 0 8px;line-height:1.35}
.hint-text{font-size:13px;line-height:1.75;color:var(--muted);white-space:pre-wrap}
.hint-block{margin-top:10px;padding-top:9px;border-top:1px solid rgba(42,65,95,.72);
  font-size:12px;line-height:1.65;color:var(--muted)}
.hint-block b{display:block;color:var(--dim);font-size:10px;letter-spacing:.12em;margin-bottom:3px}
.hint-block.question b{color:var(--blue)}
.hint-answer{margin-top:9px;padding:9px 10px;border-left:3px solid var(--green);
  background:rgba(52,211,153,.06);border-radius:0 8px 8px 0;color:#d8fff1;font-size:12px;line-height:1.7}
.hint-actions{display:flex;gap:8px;align-items:center;margin-top:10px}
.meta-list{display:grid;gap:6px;font-size:11px;color:var(--muted);line-height:1.6}
.meta-list b{color:var(--text);font-weight:600}
.controls{position:fixed;left:50%;bottom:14px;transform:translateX(-50%);width:min(1676px,calc(100vw - 44px));
  z-index:20;padding:12px 14px;display:flex;gap:9px;align-items:center;flex-wrap:wrap;
  backdrop-filter:blur(14px);background:rgba(16,32,57,.93)}
button{border:1px solid var(--border2);background:linear-gradient(180deg,var(--panel2),var(--panel3));
  color:var(--text);border-radius:9px;padding:8px 11px;font-size:12px;font-weight:700;cursor:pointer;
  transition:.15s ease;white-space:nowrap}
button:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}
button:disabled{opacity:.42;cursor:not-allowed}
button.primary{background:linear-gradient(180deg,#f7c948,#f4a90b);border-color:var(--accent);color:#261b05}
button.ghost{background:rgba(16,32,57,.4)}
.timeline{flex:1;min-width:230px;display:flex;align-items:center;gap:9px}
input[type=range]{width:100%;accent-color:var(--accent)}
select{background:var(--panel3);color:var(--text);border:1px solid var(--border2);border-radius:8px;
  padding:7px 8px;font-size:12px}
.time{font-variant-numeric:tabular-nums;color:var(--muted);font-size:11px;white-space:nowrap}
.progress{color:var(--muted);font-size:11px;white-space:nowrap}
.speed{display:flex;align-items:center;gap:5px;color:var(--muted);font-size:11px}
.footer-note{position:fixed;left:0;bottom:0;width:100%;height:0;pointer-events:none}
@media (max-width:1250px){
  .workspace{grid-template-columns:1fr}
  .teaching{grid-template-columns:minmax(240px,.9fr) minmax(300px,1.2fr);align-items:start}
  .teaching .meta-panel{grid-column:1/-1}
  .component-layout{grid-template-columns:minmax(0,.9fr) minmax(0,1fr) minmax(280px,1.2fr)}
}
@media (max-width:900px){
  .page{padding:12px 12px 150px}
  .topbar{flex-direction:column}
  .current-case{min-width:0;width:100%}
  .component-layout{grid-template-columns:1fr 1fr}
  .component[data-slot="array"],.component[data-slot="code"]{grid-column:1/-1;grid-row:auto}
  .teaching{grid-template-columns:1fr}
  .controls{bottom:7px;width:calc(100vw - 24px);padding:9px}
  .timeline{min-width:160px}
  .cell{width:58px;height:58px;font-size:21px}
}
@media (max-width:560px){
  .component-layout{grid-template-columns:1fr}
  .component[data-slot="code"]{grid-column:auto}
  .timeline{order:5;width:100%}
}
</style>
</head>
<body>
<div class="page">
  <header class="topbar panel">
    <div class="brand">
      <div class="kicker">AI 算法课堂 · 教师演示台</div>
      <h1 id="deck-title">Two Sum · 哈希表</h1>
      <div class="sub" id="deck-sub">真实执行轨迹 · 多用例 · 可手动控制 · 完全离线</div>
    </div>
    <div class="current-case">
      <div class="name" id="current-case-name">—</div>
      <div class="badges" id="current-case-badges"></div>
      <div class="input-line" id="current-case-input"></div>
      <div class="input-line" id="current-case-output"></div>
    </div>
  </header>

  <main class="workspace">
    <section class="stage">
      <div class="component-layout" id="components-root"></div>
      <section class="panel step-panel">
        <div class="step-top">
          <h2 id="step-title">步骤</h2>
          <span class="badge blue" id="step-type">—</span>
        </div>
        <div class="step-desc" id="step-desc">选择一个用例开始。</div>
        <div class="step-meta" id="step-meta"></div>
      </section>
    </section>

    <aside class="teaching">
      <section class="panel case-panel">
        <div class="panel-head"><h2>课堂用例</h2><span class="hint" id="case-count"></span></div>
        <div class="case-list" id="case-list"></div>
        <div class="case-error" id="case-error" hidden></div>
      </section>

      <section class="panel hint-panel" id="hint-panel">
        <div class="eyebrow">教学提示</div>
        <h2 id="hint-title">—</h2>
        <div class="hint-text" id="hint-explanation"></div>
        <div class="hint-block"><b>常见错误</b><span id="hint-mistake"></span></div>
        <div class="hint-block question"><b>课堂提问</b><span id="hint-question"></span></div>
        <div class="hint-actions">
          <button id="hint-toggle" class="ghost" type="button">显示参考答案</button>
        </div>
        <div class="hint-answer" id="hint-answer" hidden></div>
      </section>

      <section class="panel meta-panel">
        <div class="panel-head"><h2>本步元数据</h2><span class="badge" id="trace-verified">—</span></div>
        <div class="meta-list">
          <div>用例来源：<b id="meta-source">—</b></div>
          <div>执行状态：<b id="meta-status">—</b></div>
          <div>run_id：<b id="meta-run">—</b></div>
          <div>execution_trace_id：<b id="meta-trace">—</b></div>
          <div>真实步骤数：<b id="meta-steps">—</b></div>
        </div>
      </section>
    </aside>
  </main>
</div>

<footer class="controls panel">
  <button id="prev" type="button" title="上一步（←）">◀ 上一步</button>
  <button id="next" type="button" title="下一步（→）">下一步 ▶</button>
  <button id="play" class="primary" type="button" title="播放（空格）">▶ 播放</button>
  <button id="pause" type="button" title="暂停">⏸ 暂停</button>
  <button id="resume" type="button" title="从暂停处继续">⏵ 继续</button>
  <button id="auto" type="button" title="从头自动播放当前用例">⟲ 从头演示</button>
  <button id="reset" class="ghost" type="button" title="回到当前用例第一步">重置</button>
  <div class="timeline">
    <input id="seek" type="range" min="0" max="0" value="0" step="1" aria-label="步骤时间轴">
    <span class="time" id="progress-label">步骤 0 / 0</span>
    <span class="time" id="time-label">—</span>
  </div>
  <label class="speed" for="speed">速度
    <select id="speed">
      <option value="0.5">0.5×</option>
      <option value="1" selected>1×</option>
      <option value="1.5">1.5×</option>
      <option value="2">2×</option>
    </select>
  </label>
</footer>

<script id="classroom-data" type="application/json">__DATA__</script>
<script>
(() => {
  "use strict";
  window.__classroomErrors = [];
  window.addEventListener("error", (event) => {
    window.__classroomErrors.push(String(event.message || event.error || "unknown error"));
  });
  window.addEventListener("unhandledrejection", (event) => {
    window.__classroomErrors.push(String(event.reason || "unhandled rejection"));
  });

  const DATA = JSON.parse(document.getElementById("classroom-data").textContent);
  const CASES = DATA.cases || [];
  const CASE_MAP = new Map(CASES.map((item) => [item.case_id, item]));
  const $ = (id) => document.getElementById(id);
  const fmt = (value) => {
    if (value === null || value === undefined) return "—";
    if (typeof value === "string") return value;
    try { return JSON.stringify(value); } catch (_) { return String(value); }
  };
  const fmtPretty = (value) => {
    if (value === null || value === undefined) return "—";
    try { return JSON.stringify(value); } catch (_) { return String(value); }
  };
  const statusText = (status) => ({success:"执行成功",failed:"预期不一致",error:"执行错误",
    running:"执行中",pending:"等待执行"}[status] || status || "—");
  const statusClass = (status) => status === "success" ? "ok" : (status === "failed" ? "warn" : (status === "error" ? "bad" : ""));
  const sourceText = (source) => source === "ai_generated" ? "AI 补充" : "用户提供";
  const typeText = (type) => ({init:"初始化",visit:"访问",compare:"查询",update:"写入",found:"完成返回",
    complete:"执行完成",swap:"交换",mark:"标记",note:"说明"}[type] || type || "步骤");
  const setText = (node, text) => {
    const value = String(text == null ? "" : text);
    if (node && node.textContent !== value) node.textContent = value;
  };
  const setHTML = (node, html) => { if (node && node.innerHTML !== html) node.innerHTML = html; };
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const makeBadge = (text, cls) => {
    const node = el("span", "badge " + (cls || ""), text);
    return node;
  };
  const makePill = (text, cls) => {
    const node = el("span", "pill " + (cls || ""), text);
    return node;
  };

  // ---------------------------------------------------------------- components
  class BaseComponent {
    constructor(spec, deck) {
      this.spec = spec;
      this.deck = deck;
      this.options = spec.options || {};
      this.root = el("section", "panel component");
      this.root.dataset.componentId = spec.component_id;
      this.root.dataset.kind = spec.kind;
      this.root.dataset.slot = spec.slot;
      const head = el("div", "panel-head");
      const title = el("h2", "", this.options.title || spec.title || spec.kind);
      const hint = el("span", "hint", "");
      head.append(title, hint);
      this.root.append(head);
      this.body = el("div", "component-body");
      this.root.append(this.body);
    }
    mount(host) { host.append(this.root); this.build(); }
    build() {}
    update(_caseData, _step, _view) {}
    clear() {}
  }

  class ArrayComponent extends BaseComponent {
    build() {
      this.body.className = "component-body array-wrap";
      this.cells = el("div", "array-cells");
      this.empty = el("div", "empty", this.options.empty_text || "空数组");
      this.target = el("div", "array-target");
      this.body.append(this.cells, this.empty, this.target);
      this.cellsById = [];
    }
    ensureCell(index) {
      while (this.cellsById.length <= index) {
        const i = this.cellsById.length;
        const cell = el("div", "cell");
        const pointer = el("span", "pt");
        const value = el("span", "value");
        const idx = el("span", "idx", String(i));
        cell.append(pointer, value, idx);
        this.cells.appendChild(cell);
        this.cellsById.push({cell, pointer, value, idx});
      }
    }
    clear() {
      this.clearView();
    }
    clearView() {
      for (const item of this.cellsById) item.cell.hidden = true;
      this.empty.hidden = false;
      this.target.hidden = true;
    }
    update(caseData, step) {
      const state = step && step.state_after ? step.state_after : null;
      const arr = state && state.array ? state.array : null;
      if (!arr) { this.clearView(); return; }
      const values = Array.isArray(arr.values) ? arr.values : [];
      const pointers = arr.pointers || {};
      const found = new Set(arr.found_indices || []);
      for (let i = 0; i < values.length; i++) this.ensureCell(i);
      const visible = new Set();
      for (let i = 0; i < values.length; i++) {
        const item = this.cellsById[i];
        visible.add(item);
        item.cell.hidden = false;
        setText(item.value, fmt(values[i]));
        setText(item.idx, String(i));
        const labels = Object.entries(pointers)
          .filter(([, value]) => Number(value) === i)
          .map(([name, value]) => `${name} = ${fmt(value)}`);
        setText(item.pointer, labels.join(" · "));
        item.pointer.hidden = labels.length === 0;
        item.cell.classList.toggle("active", labels.length > 0);
        item.cell.classList.toggle("found", found.has(i));
      }
      for (const item of this.cellsById) {
        if (!visible.has(item)) item.cell.hidden = true;
      }
      this.empty.hidden = values.length > 0;
      this.empty.textContent = this.options.empty_text || "空数组";
      const hasTarget = arr.target !== null && arr.target !== undefined;
      this.target.hidden = !hasTarget;
      setText(this.target, hasTarget ? `target = ${fmt(arr.target)}` : "");
    }
  }

  class HashMapComponent extends BaseComponent {
    build() {
      this.body.className = "component-body";
      this.lookupBar = el("div", "lookup");
      this.empty = el("div", "empty", this.options.empty_text || "{ } 空哈希表");
      this.tableWrap = el("div", "table-wrap");
      this.table = el("table");
      this.thead = el("thead");
      this.tbody = el("tbody");
      const headerRow = el("tr");
      headerRow.append(el("th", "", this.options.key_header || "key"),
                       el("th", "", this.options.value_header || "value"));
      this.thead.append(headerRow);
      this.table.append(this.thead, this.tbody);
      this.tableWrap.append(this.table);
      this.body.append(this.empty, this.tableWrap, this.lookupBar);
      this.rows = new Map();
    }
    ensureRow(key) {
      if (this.rows.has(key)) return this.rows.get(key);
      const tr = el("tr");
      const keyCell = el("td");
      const valueCell = el("td");
      tr.append(keyCell, valueCell);
      this.tbody.append(tr);
      const item = {tr, keyCell, valueCell};
      this.rows.set(key, item);
      return item;
    }
    clear() { this.clearView(); }
    clearView() {
      this.tbody.replaceChildren();
      this.rows.clear();
      this.tableWrap.hidden = true;
      this.empty.hidden = false;
      setText(this.lookupBar, "");
      this.lookupBar.replaceChildren(makePill("等待查找", "none"));
    }
    update(caseData, step) {
      const state = step && step.state_after ? step.state_after : null;
      const d = state && state.dict_state ? state.dict_state : null;
      if (!d) { this.clearView(); return; }
      const entries = Array.isArray(d.entries) ? d.entries : [];
      const activeKeys = new Set(entries.map((entry) => String(entry.key)));
      for (const [key, item] of this.rows) {
        if (!activeKeys.has(String(key))) {
          item.tr.remove();
          this.rows.delete(key);
        }
      }
      for (const entry of entries) {
        const key = String(entry.key);
        const item = this.ensureRow(key);
        setText(item.keyCell, key);
        setText(item.valueCell, fmt(entry.value));
        const lookupHit = d.lookup_status === "hit" && String(d.lookup_key) === key;
        const fresh = String((step && step.meta && step.meta.key) || "") === key && step.type === "update";
        item.tr.classList.toggle("hit", Boolean(entry.highlighted) || lookupHit);
        item.tr.classList.toggle("fresh", fresh);
        this.tbody.appendChild(item.tr);
      }
      const hasEntries = entries.length > 0;
      this.tableWrap.hidden = !hasEntries;
      this.empty.hidden = hasEntries;
      this.empty.textContent = this.options.empty_text || "{ } 空哈希表";
      this.lookupBar.replaceChildren();
      if (d.lookup_key !== null && d.lookup_key !== undefined) {
        const status = d.lookup_status === "hit" ? "hit" : (d.lookup_status === "miss" ? "miss" : "none");
        const text = status === "hit" ? (this.options.hit_text || "HIT")
          : (status === "miss" ? (this.options.miss_text || "MISS") : "—");
        this.lookupBar.append(el("span", "", `查找 ${fmt(d.lookup_key)} →`),
          makePill(text, status));
      } else {
        this.lookupBar.append(makePill(this.options.waiting_text || "等待下一次查找", "none"));
      }
    }
  }

  class VariableComponent extends BaseComponent {
    build() {
      this.body.className = "component-body vars";
      this.empty = el("div", "empty", this.options.empty_text || "暂无变量");
      this.rowsRoot = el("div", "vars");
      this.body.classList.remove("vars");
      this.body.append(this.empty, this.rowsRoot);
      this.rows = new Map();
    }
    clear() { this.clearView(); }
    clearView() {
      this.rowsRoot.replaceChildren();
      this.rows.clear();
      this.empty.hidden = false;
      setText(this.empty, this.options.empty_text || "暂无变量");
    }
    update(_caseData, _step, view) {
      const variables = view && Array.isArray(view.variables) ? view.variables : [];
      if (!variables.length) { this.clearView(); return; }
      this.empty.hidden = true;
      const active = new Set(variables.map((item) => String(item.label)));
      for (const [label, item] of this.rows) {
        if (!active.has(String(label))) {
          item.node.remove();
          this.rows.delete(label);
        }
      }
      for (const item of variables) {
        const label = String(item.label);
        let row = this.rows.get(label);
        if (!row) {
          const node = el("div", "var");
          const labelNode = el("span", "label", label);
          const valueNode = el("span", "value", fmt(item.value));
          node.append(labelNode, valueNode);
          this.rowsRoot.append(node);
          row = {node, labelNode, valueNode};
          this.rows.set(label, row);
        }
        setText(row.labelNode, label);
        setText(row.valueNode, fmt(item.value));
        row.node.classList.toggle("changed", Boolean(item.changed));
      }
    }
  }

  class CodeComponent extends BaseComponent {
    build() {
      this.body.className = "component-body";
      this.scroll = el("div", "code-scroll");
      this.body.append(this.scroll);
      this.lines = [];
      const code = String(this.deck.code || "");
      const lines = code.split("\n");
      if (lines.length === 1 && lines[0] === "") lines.length = 0;
      this.lines = lines.map((line, index) => {
        const row = el("div", "code-line");
        const no = el("span", "no", String(index + 1));
        const text = el("span", "text", line || " ");
        row.append(no, text);
        this.scroll.append(row);
        return {row, text};
      });
      if (!this.lines.length) this.body.append(el("div", "empty", "没有源码"));
    }
    clear() { this.setActive(null); }
    setActive(lineNumber) {
      for (let i = 0; i < this.lines.length; i++) {
        this.lines[i].row.classList.toggle("active", Number(lineNumber) === i + 1);
      }
      if (lineNumber != null && this.lines[Number(lineNumber) - 1]) {
        const node = this.lines[Number(lineNumber) - 1].row;
        const top = node.offsetTop;
        if (top < this.scroll.scrollTop || top > this.scroll.scrollTop + this.scroll.clientHeight - 30) {
          this.scroll.scrollTop = Math.max(0, top - this.scroll.clientHeight / 2);
        }
      }
    }
    update(_caseData, step) {
      this.setActive(step && step.code_line ? step.code_line : null);
    }
  }

  class FallbackComponent extends BaseComponent {
    update(_caseData, _step) {
      this.body.textContent = "未实现的组件类型：" + this.spec.kind;
    }
  }

  const COMPONENT_CLASSES = {
    array: ArrayComponent,
    hash_map: HashMapComponent,
    variables: VariableComponent,
    code: CodeComponent,
  };
  const components = new Map();

  function mountComponents() {
    const host = $("components-root");
    host.replaceChildren();
    components.clear();
    for (const spec of DATA.visual_plan.components || []) {
      const ComponentClass = COMPONENT_CLASSES[spec.kind] || FallbackComponent;
      const component = new ComponentClass(spec, DATA);
      component.mount(host);
      components.set(spec.component_id, component);
    }
  }

  // ---------------------------------------------------------------- playback
  class ClassroomPlayback {
    constructor({defaultStepDuration, onRender, onState}) {
      this.defaultStepDuration = Math.max(0.2, Number(defaultStepDuration) || 1.2);
      this.onRender = onRender;
      this.onState = onState;
      this.caseId = DATA.active_case_id;
      this.index = 0;
      this.mode = "teacher";
      this.speed = 1;
      this.playing = false;
      this.timer = null;
      this.token = 0;
    }
    get currentCase() { return CASE_MAP.get(this.caseId) || null; }
    get trace() { const c = this.currentCase; return c && c.trace ? c.trace : null; }
    get steps() { return this.trace ? (this.trace.steps || []) : []; }
    get hasTrace() { return this.steps.length > 0; }
    get atEnd() { return this.hasTrace && this.index >= this.steps.length - 1; }
    durationAt(index) {
      const step = this.steps[index];
      return step && Number(step.duration) > 0 ? Number(step.duration) : this.defaultStepDuration;
    }
    totalDuration() {
      let total = 0;
      for (let i = 0; i < this.steps.length; i++) total += this.durationAt(i);
      return total;
    }
    elapsed() {
      let total = 0;
      for (let i = 0; i < this.index; i++) total += this.durationAt(i);
      return total;
    }
    snapshot() {
      const step = this.steps[this.index] || null;
      return {
        caseId: this.caseId,
        index: this.index,
        count: this.steps.length,
        mode: this.mode,
        speed: this.speed,
        playing: this.playing,
        atEnd: this.atEnd,
        stepId: step ? step.step_id : null,
        stepType: step ? step.type : null,
      };
    }
    render() {
      if (this.onRender) this.onRender(this.currentCase, this.steps[this.index] || null, this.index);
      if (this.onState) this.onState(this.snapshot());
    }
    stateOnly() { if (this.onState) this.onState(this.snapshot()); }
    cancelTimer() {
      this.token += 1;
      if (this.timer !== null) {
        clearTimeout(this.timer);
        this.timer = null;
      }
    }
    schedule() {
      if (!this.playing || !this.hasTrace) return;
      this.cancelTimer();
      const token = this.token;
      const delay = Math.max(120, (this.durationAt(this.index) / this.speed) * 1000);
      this.timer = setTimeout(() => this.onTimer(token), delay);
    }
    onTimer(token) {
      if (token !== this.token || !this.playing) return;
      this.timer = null;
      if (!this.hasTrace || this.atEnd) {
        this.playing = false;
        this.mode = "teacher";
        this.stateOnly();
        return;
      }
      this.index += 1;
      this.mode = "auto";
      this.render();
      this.schedule();
    }
    loadCase(caseId) {
      this.cancelTimer();
      this.caseId = caseId;
      this.index = 0;
      this.mode = "teacher";
      this.playing = false;
      this.render();
    }
    manual(index) {
      if (!this.hasTrace) return;
      this.cancelTimer();
      this.playing = false;
      this.mode = "teacher";
      this.index = Math.max(0, Math.min(this.steps.length - 1, Number(index) || 0));
      this.render();
    }
    next() { this.manual(this.index + 1); }
    prev() { this.manual(this.index - 1); }
    seek(index) { this.manual(index); }
    reset() { this.manual(0); }
    play() {
      if (!this.hasTrace) return;
      this.cancelTimer();
      if (this.atEnd) this.index = 0;
      this.mode = "auto";
      this.playing = true;
      this.render();
      this.schedule();
    }
    autoPlay() {
      if (!this.hasTrace) return;
      this.cancelTimer();
      this.index = 0;
      this.mode = "auto";
      this.playing = true;
      this.render();
      this.schedule();
    }
    pause() {
      if (!this.playing) return;
      this.cancelTimer();
      this.playing = false;
      this.mode = "teacher";
      this.stateOnly();
    }
    resume() {
      if (!this.hasTrace || this.playing) return;
      this.cancelTimer();
      if (this.atEnd) this.index = 0;
      this.mode = "auto";
      this.playing = true;
      this.render();
      this.schedule();
    }
    setSpeed(speed) {
      const value = Number(speed);
      if (!Number.isFinite(value) || value <= 0) return;
      this.speed = value;
      if (this.playing) this.schedule();
      this.stateOnly();
    }
  }

  // ---------------------------------------------------------------- rendering
  class TeachingHintComponent {
    constructor() {
      this.currentHint = null;
      this.answerVisible = false;
      this.panel = $("hint-panel");
      this.toggle = $("hint-toggle");
      this.answer = $("hint-answer");
      this.toggle.addEventListener("click", () => this.toggleAnswer());
    }
    render(hint) {
      this.currentHint = hint;
      this.answerVisible = false;
      this.panel.classList.toggle("no-hint", !hint);
      setText($("hint-title"), hint ? hint.title : "本步骤暂无教学提示");
      setText($("hint-explanation"), hint ? hint.explanation : "当前执行步骤没有附带教学素材。继续播放或选择有提示的步骤。");
      setText($("hint-mistake"), hint && hint.common_mistake ? hint.common_mistake : "—");
      setText($("hint-question"), hint && hint.question ? hint.question : "—");
      this.answer.hidden = true;
      this.answer.textContent = hint ? (hint.answer || "") : "";
      this.toggle.disabled = !hint || !hint.answer;
      setText(this.toggle, "显示参考答案");
    }
    toggleAnswer() {
      if (!this.currentHint || !this.currentHint.answer) return;
      this.answerVisible = !this.answerVisible;
      this.answer.hidden = !this.answerVisible;
      setText(this.toggle, this.answerVisible ? "收起参考答案" : "显示参考答案");
    }
  }

  class PlaybackControls {
    constructor() {
      this.controller = null;
      $("prev").addEventListener("click", () => this.controller && this.controller.prev());
      $("next").addEventListener("click", () => this.controller && this.controller.next());
      $("play").addEventListener("click", () => this.controller && this.controller.play());
      $("pause").addEventListener("click", () => this.controller && this.controller.pause());
      $("resume").addEventListener("click", () => this.controller && this.controller.resume());
      $("auto").addEventListener("click", () => this.controller && this.controller.autoPlay());
      $("reset").addEventListener("click", () => this.controller && this.controller.reset());
      $("seek").addEventListener("input", (event) => {
        if (this.controller) this.controller.seek(Number(event.target.value));
      });
      $("speed").addEventListener("change", (event) => {
        if (this.controller) this.controller.setSpeed(Number(event.target.value));
      });
      document.addEventListener("keydown", (event) => {
        if (event.target && /INPUT|SELECT|TEXTAREA/.test(event.target.tagName)) return;
        if (!this.controller) return;
        if (event.code === "Space") {
          event.preventDefault();
          if (this.controller.playing) this.controller.pause();
          else this.controller.play();
        } else if (event.code === "ArrowLeft") {
          event.preventDefault(); this.controller.prev();
        } else if (event.code === "ArrowRight") {
          event.preventDefault(); this.controller.next();
        } else if (event.code === "Home") {
          event.preventDefault(); this.controller.reset();
        } else if (event.code === "End") {
          event.preventDefault(); this.controller.seek(this.controller.steps.length - 1);
        }
      });
    }
    bind(controller) { this.controller = controller; }
    render(state) {
      const hasTrace = state.count > 0;
      $("prev").disabled = !hasTrace || state.index <= 0;
      $("next").disabled = !hasTrace || state.atEnd;
      $("play").disabled = !hasTrace || state.playing;
      $("pause").disabled = !hasTrace || !state.playing;
      $("resume").disabled = !hasTrace || state.playing;
      $("auto").disabled = !hasTrace;
      $("reset").disabled = !hasTrace;
      $("seek").disabled = !hasTrace;
      $("speed").disabled = !hasTrace;
      $("speed").value = String(state.speed);
      if (hasTrace && this.controller) {
        $("seek").max = String(Math.max(0, state.count - 1));
        $("seek").value = String(state.index);
        setText($("progress-label"), `步骤 ${state.index + 1} / ${state.count}`);
        const total = this.controller.totalDuration();
        const elapsed = this.controller.elapsed();
        setText($("time-label"), `${elapsed.toFixed(1)}s / ${total.toFixed(1)}s`);
      } else {
        setText($("progress-label"), "步骤 0 / 0");
        setText($("time-label"), "—");
      }
      $("play").textContent = state.playing ? "▶ 播放中" : "▶ 播放";
    }
  }

  let lastActiveCaseId = null;

  function renderCaseChrome(caseData) {
    setText($("current-case-name"), caseData.name || caseData.case_id);
    const badges = $("current-case-badges");
    badges.replaceChildren(
      makeBadge(sourceText(caseData.source), caseData.source === "ai_generated" ? "blue" : ""),
      makeBadge(statusText(caseData.status), statusClass(caseData.status)),
      makeBadge(caseData.trace && caseData.trace.verified ? "真实轨迹 · 已验证" : "真实轨迹未验证",
        caseData.trace && caseData.trace.verified ? "ok" : "warn")
    );
    setText($("current-case-input"), "输入：" + fmtPretty(caseData.input_data));
    const expectedText = caseData.expected_output === null || caseData.expected_output === undefined
      ? "未提供" : fmtPretty(caseData.expected_output);
    const actualText = caseData.actual_output === null || caseData.actual_output === undefined
      ? "无结果" : fmtPretty(caseData.actual_output);
    setText($("current-case-output"), `expected：${expectedText}  ·  actual：${actualText}`);
    const error = $("case-error");
    error.hidden = !caseData.error;
    setText(error, caseData.error || "");
    document.querySelectorAll(".case-card").forEach((card) => {
      card.classList.toggle("active", card.dataset.caseId === caseData.case_id);
    });
    if (lastActiveCaseId !== caseData.case_id) {
      lastActiveCaseId = caseData.case_id;
      const active = document.querySelector(".case-card.active");
      if (active) active.scrollIntoView({block: "nearest"});
    }
    setText($("case-count"), `${CASES.length} 个用例`);
    setText($("meta-source"), sourceText(caseData.source));
    setText($("meta-status"), statusText(caseData.status));
    setText($("meta-run"), caseData.run_id || "—");
    setText($("meta-trace"), caseData.trace ? (caseData.trace.metadata.execution_trace_id || "—") : "—");
    setText($("meta-steps"), caseData.trace ? String((caseData.trace.steps || []).length) : "0");
    const verified = $("trace-verified");
    verified.className = "badge " + (caseData.trace && caseData.trace.verified ? "ok" : "warn");
    setText(verified, caseData.trace && caseData.trace.verified ? "已验证" : "未验证");
  }

  function renderNoTrace(caseData) {
    renderCaseChrome(caseData);
    for (const component of components.values()) {
      if (component.clear) component.clear();
    }
    setText($("step-title"), "不可播放");
    setText($("step-type"), "ERROR");
    setText($("step-desc"), caseData.error || "该用例没有 AnimationTrace，无法播放。");
    setText($("step-meta"), "请选择带真实执行轨迹的用例。");
    hintView.render(null);
    setText($("progress-label"), "步骤 0 / 0");
    setText($("time-label"), "—");
    const seek = $("seek");
    seek.min = "0"; seek.max = "0"; seek.value = "0"; seek.disabled = true;
  }

  function renderStep(caseData, step, index) {
    renderCaseChrome(caseData);
    const steps = (caseData.trace && caseData.trace.steps) || [];
    const views = caseData.step_views || [];
    const view = views.find((item) => item.step_id === (step ? step.step_id : -1)) || null;
    for (const component of components.values()) {
      component.update(caseData, step, view);
    }
    if (!step) { renderNoTrace(caseData); return; }
    setText($("step-title"), `步骤 ${index + 1} / ${steps.length}`);
    setText($("step-type"), typeText(step.type));
    setText($("step-desc"), step.description || step.narration || "");
    setText($("step-meta"),
      `code_line=${step.code_line == null ? "—" : step.code_line} · step_id=${step.step_id} · trace_id=${caseData.trace.metadata.execution_trace_id || "—"}`);
    const hint = (caseData.hints || []).find((item) => item.related_step_id === step.step_id) || null;
    hintView.render(hint);
    const seek = $("seek");
    seek.disabled = false;
    seek.min = "0";
    seek.max = String(Math.max(0, steps.length - 1));
    seek.value = String(index);
    setText($("progress-label"), `步骤 ${index + 1} / ${steps.length}`);
  }

  function buildCaseList() {
    const list = $("case-list");
    list.replaceChildren();
    for (const item of CASES) {
      const card = el("button", "case-card");
      card.type = "button";
      card.dataset.caseId = item.case_id;
      const row = el("div", "row");
      const name = el("span", "name", item.name || item.case_id);
      const badge = makeBadge(statusText(item.status), statusClass(item.status));
      row.append(name, badge);
      const input = el("div", "input", fmtPretty(item.input_data));
      card.append(row, input);
      card.addEventListener("click", () => controller.loadCase(item.case_id));
      list.append(card);
    }
  }

  // ---------------------------------------------------------------- boot
  mountComponents();
  buildCaseList();
  const hintView = new TeachingHintComponent();
  const controls = new PlaybackControls();
  const controller = new ClassroomPlayback({
    defaultStepDuration: DATA.default_step_duration,
    onRender: renderStep,
    onState: (state) => controls.render(state),
  });
  controls.bind(controller);

  document.title = (DATA.title || "Two Sum · 哈希表") + " · 课堂演示台";
  $("deck-title").textContent = DATA.title || "Two Sum · 哈希表";
  $("deck-sub").textContent = `真实执行轨迹 · ${CASES.length} 个用例 · 手动/自动共享同一条轨迹 · 完全离线`;
  controller.loadCase(DATA.active_case_id);

  window.__classroom = {
    controller,
    components,
    deck: DATA,
    getState: () => controller.snapshot(),
    getErrors: () => window.__classroomErrors.slice(),
  };
  window.__classroomReady = true;
})();
</script>
</body>
</html>
"""
