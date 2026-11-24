"""生成完全离线、无后端依赖的 interactive.html。

播放器只嵌入统一的 AnimationTrace（以及教学计划中的逐步时间轴），
所有跳转都从 AnimationStep.state_after 重建状态，不依赖 Manim 视频。
"""
from __future__ import annotations

import json
from pathlib import Path

from ..protocol.events import Trace
from ..protocol.m2 import M2SectionKind, TeachingPlan


def _json_for_html(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _stepwise_timeline(plan: TeachingPlan, trace: Trace) -> list[dict[str, float | int]]:
    video = next((item for item in plan.videos if item.variant == "step_by_step"), None)
    if video is not None:
        section = next((item for item in video.sections if item.kind == M2SectionKind.STEPWISE), None)
        if section is not None and section.step_timings:
            # 播放器时间轴只覆盖“逐步讲解”的步骤，从第一个 step 开始归零。
            base = section.step_timings[0].start
            return [
                {
                    "step_id": timing.step_id,
                    "start": round(timing.start - base, 4),
                    "duration": round(timing.duration, 4),
                }
                for timing in section.step_timings
            ]
    return [
        {"step_id": step.step_id, "start": float(index * 2), "duration": 2.0}
        for index, step in enumerate(trace.steps)
    ]


def write_html_player(trace: Trace, plan: TeachingPlan, path: str | Path) -> Path:
    path = Path(path)
    payload = {
        "trace": trace.model_dump(mode="json"),
        "teaching": plan.model_dump(mode="json"),
        "step_timeline": _stepwise_timeline(plan, trace),
    }
    data = _json_for_html(payload)
    html = TEMPLATE.replace("__DATA__", data)
    path.write_text(html, encoding="utf-8")
    return path


TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Two Sum · 交互式执行回放</title>
<style>
:root{
  --bg:#0b1220;--panel:#16233d;--panel2:#1c2b49;--border:#2a3b5e;--text:#e8eef9;
  --muted:#9aa9c2;--accent:#fbbf24;--compare:#38bdf8;--sorted:#34d399;--danger:#f87171;
  --code:#0f172a;--mx:#0c1526;
}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);
  font-family:"Microsoft YaHei","PingFang SC","Noto Sans CJK SC",sans-serif}
body{padding:18px 22px 30px}
header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;
  max-width:1480px;margin:0 auto 12px}
h1{font-size:22px;margin:0 0 5px;letter-spacing:.2px}
.sub{color:var(--muted);font-size:13px}
.badge{display:inline-block;border:1px solid var(--border);background:var(--panel);
  color:var(--muted);border-radius:999px;padding:4px 10px;font-size:12px;margin-left:6px}
.badge.ok{color:var(--sorted);border-color:#256a55}
.layout{max-width:1480px;margin:0 auto;display:grid;grid-template-columns:minmax(0,1.55fr) minmax(320px,.85fr);
  gap:16px;align-items:start}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:14px}
.panel h2{font-size:14px;color:var(--muted);margin:0 0 10px;font-weight:700;letter-spacing:.6px}
.visual{display:grid;gap:12px}
.array-wrap{display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap;
  min-height:92px;padding:8px 4px}
.cell{position:relative;width:68px;height:68px;border:2px solid var(--border);border-radius:12px;
  background:var(--panel2);display:flex;align-items:center;justify-content:center;
  font-size:24px;font-weight:700;transition:.18s ease}
.cell .idx{position:absolute;bottom:-24px;color:var(--muted);font-size:12px;font-weight:400}
.cell.active{border-color:var(--accent);background:rgba(251,191,36,.18);color:#fff}
.cell.found{border-color:var(--sorted);background:rgba(52,211,153,.22);color:#eafff7}
.cell .pt{position:absolute;top:-24px;color:var(--accent);font-size:11px;white-space:nowrap}
.target{margin-left:14px;color:var(--accent);font-size:13px;white-space:nowrap}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:12px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:8px 6px;border-bottom:1px solid rgba(42,59,94,.75)}
th{color:var(--muted);font-size:12px;font-weight:600}
tr.hit td{color:var(--accent)}
.empty{color:var(--muted);font-size:13px;padding:8px 0}
.lookup{display:flex;align-items:center;gap:8px;margin-top:10px;font-size:13px;color:var(--muted);min-height:28px}
.pill{border-radius:999px;padding:3px 10px;font-size:11px;font-weight:700;letter-spacing:.5px}
.pill.hit{color:var(--sorted);border:1px solid var(--sorted);background:rgba(52,211,153,.12)}
.pill.miss{color:var(--danger);border:1px solid var(--danger);background:rgba(248,113,113,.1)}
.pill.none{color:var(--muted);border:1px solid var(--border)}
.vars{display:grid;grid-template-columns:1fr 1fr;gap:8px 12px}
.var{background:var(--panel2);border:1px solid var(--border);border-radius:9px;padding:7px 9px}
.var small{display:block;color:var(--muted);font-size:11px;margin-bottom:2px}
.var b{font-size:15px;word-break:break-all}
.code{background:var(--code);border:1px solid var(--border);border-radius:12px;padding:10px 8px;
  font-family:"Cascadia Mono",Consolas,monospace;font-size:12.5px;line-height:1.52;overflow:auto}
.code .line{display:flex;gap:10px;padding:2px 5px;border-radius:5px;white-space:pre}
.code .no{color:#52627e;width:22px;text-align:right;flex:none;user-select:none}
.code .line.active{background:rgba(251,191,36,.16);box-shadow:inset 3px 0 0 var(--accent)}
.step-head{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:8px}
.step-head h2{margin:0;color:var(--text);font-size:15px}
.step-desc{color:var(--muted);font-size:13px;line-height:1.6;min-height:42px}
.meta{color:var(--muted);font-size:12px;line-height:1.7;margin-top:6px}
.complexity{margin-top:12px;border-top:1px solid var(--border);padding-top:10px;color:var(--muted);
  font-size:12px;line-height:1.65}
.controls{max-width:1480px;margin:14px auto 0;background:var(--panel);border:1px solid var(--border);
  border-radius:14px;padding:12px 14px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
button{border:1px solid var(--border);background:var(--panel2);color:var(--text);border-radius:9px;
  padding:8px 12px;font-size:13px;cursor:pointer;transition:.15s}
button:hover{border-color:var(--accent);color:var(--accent)}
button.primary{background:var(--accent);border-color:var(--accent);color:#1b1607;font-weight:700}
input[type=range]{accent-color:var(--accent)}
.timeline{flex:1;min-width:260px;display:flex;align-items:center;gap:10px}
.timeline input{width:100%}
.time{font-variant-numeric:tabular-nums;color:var(--muted);font-size:12px;white-space:nowrap}
.chips{max-width:1480px;margin:10px auto 0;display:flex;gap:6px;flex-wrap:wrap}
.chip{border:1px solid var(--border);background:var(--panel2);color:var(--muted);border-radius:999px;
  padding:5px 9px;font-size:11px;cursor:pointer}
.chip.active{border-color:var(--accent);color:var(--accent)}
footer{max-width:1480px;margin:16px auto 0;color:var(--muted);font-size:11px;line-height:1.7}
@media (max-width:900px){.layout{grid-template-columns:1fr}.cards{grid-template-columns:1fr}
  .cell{width:54px;height:54px;font-size:20px}}
</style>
</head>
<body>
<header>
  <div>
    <h1 id="title">Two Sum · 交互式执行回放</h1>
    <div class="sub" id="subtitle">真实执行轨迹 · 可任意跳转 · 完全离线</div>
  </div>
  <div><span class="badge ok" id="verified">真实轨迹</span><span class="badge" id="trace-id"></span></div>
</header>

<div class="layout">
  <div class="visual">
    <section class="panel">
      <h2>数组 nums</h2>
      <div class="array-wrap" id="array"></div>
    </section>
    <div class="cards">
      <section class="panel">
        <h2>哈希表 seen</h2>
        <div id="dict"></div>
        <div class="lookup" id="lookup"></div>
      </section>
      <section class="panel">
        <h2>关键变量</h2>
        <div class="vars" id="vars"></div>
        <div class="meta" id="vars-note">值来自 state_after</div>
      </section>
    </div>
  </div>
  <div>
    <section class="panel">
      <div class="step-head"><h2 id="step-title">步骤</h2><span class="badge" id="step-type"></span></div>
      <div class="step-desc" id="step-desc"></div>
      <div class="meta" id="step-meta"></div>
      <div class="code" id="code"></div>
      <div class="complexity" id="complexity"></div>
    </section>
  </div>
</div>

<div class="controls">
  <button id="prev" title="上一步（←）">◀ 上一步</button>
  <button id="play" class="primary" title="播放/暂停（空格）">▶ 播放</button>
  <button id="next" title="下一步（→）">下一步 ▶</button>
  <div class="timeline">
    <input id="seek" type="range" min="0" max="1000" value="0" step="1" aria-label="时间轴">
    <span class="time" id="time">00:00 / 00:00</span>
  </div>
  <label class="time" for="speed">速度</label>
  <select id="speed" style="background:var(--panel2);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:7px">
    <option value="0.5">0.5×</option>
    <option value="1" selected>1×</option>
    <option value="1.5">1.5×</option>
    <option value="2">2×</option>
  </select>
  <button id="reset" title="回到第一步">重置</button>
</div>
<div class="chips" id="chips"></div>

<footer>
  数据来源：<code>animation_events.json</code> + <code>teaching_plan.json</code>。本页不请求后端、不依赖视频文件；
  播放器只按 <code>AnimationStep.state_after</code> 重建状态。
</footer>

<script id="trace-data" type="application/json">__DATA__</script>
<script>
(() => {
  "use strict";
  const DATA = JSON.parse(document.getElementById("trace-data").textContent);
  const TRACE = DATA.trace;
  const PLAN = DATA.teaching;
  const STEPS = TRACE.steps || [];
  const TIMELINE = DATA.step_timeline || [];
  const CODE_LINES = (TRACE.metadata.code || "").split("\n");
  const TOTAL = Math.max(TIMELINE.reduce((a, x) => a + Number(x.duration || 0), 0), 0.01);
  let index = 0;
  let elapsed = 0;
  let playing = false;
  let speed = 1;
  let raf = null;
  let lastTs = 0;

  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v == null ? "" : v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const fmt = (v) => (typeof v === "number" && Number.isInteger(v)) ? String(v) : String(v == null ? "—" : v);
  const pad = (n) => String(n).padStart(2, "0");
  const clock = (s) => {
    s = Math.max(0, Number(s) || 0);
    return pad(Math.floor(s / 60)) + ":" + pad(Math.floor(s % 60));
  };

  function stepAt(i) {
    return STEPS[Math.max(0, Math.min(STEPS.length - 1, i))] || {state_after:{array:{values:[]}}};
  }
  function timingAt(i) {
    return TIMELINE[Math.max(0, Math.min(TIMELINE.length - 1, i))] || {start:0,duration:2};
  }
  function stepStart(i) {
    return Number(timingAt(i).start || 0);
  }
  function stepDuration(i) {
    return Math.max(0.2, Number(timingAt(i).duration || 2));
  }
  function absoluteElapsed() {
    return stepStart(index) + Math.min(elapsed, stepDuration(index));
  }

  function renderArray(state) {
    const arr = state.array || {values: []};
    const values = arr.values || [];
    const active = arr.pointers && arr.pointers.i;
    const found = new Set(arr.found_indices || []);
    const target = arr.target;
    const items = values.map((value, i) => {
      const cls = found.has(i) ? "cell found" : ((active != null && Number(active) === i) ? "cell active" : "cell");
      const pointer = (active != null && Number(active) === i) ? `<span class="pt">i = ${i}</span>` : "";
      return `<div class="${cls}" data-index="${i}" data-value="${esc(value)}">${pointer}${esc(fmt(value))}<span class="idx">${i}</span></div>`;
    });
    if (target != null) items.push(`<span class="target">target = ${esc(fmt(target))}</span>`);
    $("array").innerHTML = items.join("") || '<span class="empty">—</span>';
  }

  function renderDict(state) {
    const d = state.dict_state || {entries: [], lookup_key: null, lookup_status: null};
    const entries = d.entries || [];
    if (!entries.length) {
      $("dict").innerHTML = '<div class="empty">{ }  空哈希表</div>';
    } else {
      const rows = entries.map((e) => {
        const hit = e.highlighted || (d.lookup_status === "hit" && String(d.lookup_key) === String(e.key));
        return `<tr class="${hit ? "hit" : ""}"><td>${esc(e.key)}</td><td>${esc(fmt(e.value))}</td></tr>`;
      }).join("");
      $("dict").innerHTML = `<table><thead><tr><th>key</th><th>index</th></tr></thead><tbody>${rows}</tbody></table>`;
    }
    let badge = '<span class="pill none">等待查找</span>';
    if (d.lookup_key != null) {
      const status = d.lookup_status === "hit" ? "hit" : (d.lookup_status === "miss" ? "miss" : "none");
      const text = d.lookup_status === "hit" ? "HIT" : (d.lookup_status === "miss" ? "MISS" : "—");
      badge = `<span>查找 <b>${esc(d.lookup_key)}</b> →</span><span class="pill ${status}">${text}</span>`;
    }
    $("lookup").innerHTML = badge;
  }

  function renderVars(state) {
    const byName = {};
    (state.variables || []).forEach((v) => { byName[v.name] = v; });
    const target = state.array ? state.array.target : null;
    const seenSize = state.dict_state ? (state.dict_state.entries || []).length : 0;
    const rows = [
      ["i", byName.i ? byName.i.value : "—"],
      ["x", byName.x ? byName.x.value : "—"],
      ["need", byName.need ? byName.need.value : "—"],
      ["target", target == null ? "—" : fmt(target)],
      ["seen.size", seenSize],
    ];
    $("vars").innerHTML = rows.map(([k, v]) =>
      `<div class="var"><small>${k}</small><b>${esc(v)}</b></div>`).join("");
  }

  function renderCode(step) {
    const active = Number(step.code_line || 0);
    const lines = CODE_LINES.map((line, i) => {
      const n = i + 1;
      return `<div class="line ${n === active ? "active" : ""}" data-line="${n}"><span class="no">${n}</span><span>${esc(line || " ")}</span></div>`;
    });
    $("code").innerHTML = lines.join("");
    $("code").dataset.activeLine = active ? String(active) : "";
  }

  function renderComplexity() {
    const c = PLAN.complexity;
    if (!c) return;
    const o = c.observed || {};
    $("complexity").innerHTML =
      `<b>复杂度三分解</b> · 理论 ${esc(c.theory_time)} / ${esc(c.theory_space)}` +
      ` · 用户代码 ${esc(c.code_time)} / ${esc(c.code_space)}` +
      `<br>本次实测：n=${esc(o.n)}，访问 ${esc(o.visited)}，查找 ${esc(o.lookups)}` +
      `（${esc(o.hits)} hit / ${esc(o.misses)} miss），插入 ${esc(o.inserts)}，` +
      `seen 峰值 ${esc(o.peak_seen)}，耗时 ${esc(o.duration_ms)} ms。`;
  }

  function render() {
    if (!STEPS.length) return;
    index = Math.max(0, Math.min(STEPS.length - 1, index));
    const step = stepAt(index);
    const state = step.state_after || {};
    const typeMap = {init:"初始化",visit:"访问",compare:"查找",update:"写入",found:"命中",complete:"完成",
      swap:"交换",mark:"标记",note:"说明"};
    $("step-title").textContent = `步骤 ${index + 1} / ${STEPS.length}`;
    $("step-type").textContent = typeMap[step.type] || step.type || "步骤";
    $("step-desc").textContent = step.description || step.narration || "";
    $("step-meta").innerHTML =
      `当前代码行：<b>${esc(step.code_line == null ? "—" : step.code_line)}</b>` +
      ` · 真实状态摘要：${esc((PLAN.steps && PLAN.steps[index] && PLAN.steps[index].state_sha256 || "").slice(0, 12))}…` +
      ` · step_id=${esc(step.step_id)}`;
    renderArray(state);
    renderDict(state);
    renderVars(state);
    renderCode(step);
    renderComplexity();
    document.querySelectorAll(".chip").forEach((chip) => {
      chip.classList.toggle("active", Number(chip.dataset.step) === index);
    });
    $("seek").value = String(Math.round((absoluteElapsed() / TOTAL) * 1000));
    $("time").textContent = `${clock(absoluteElapsed())} / ${clock(TOTAL)}`;
    $("prev").disabled = index <= 0;
    $("next").disabled = index >= STEPS.length - 1;
  }

  function setStep(i, at = 0) {
    index = Math.max(0, Math.min(STEPS.length - 1, i));
    elapsed = Math.max(0, Math.min(at, stepDuration(index)));
    render();
  }

  function seekAbsolute(seconds) {
    seconds = Math.max(0, Math.min(TOTAL, Number(seconds) || 0));
    let i = 0;
    while (i < TIMELINE.length - 1 && stepStart(i + 1) <= seconds) i++;
    setStep(i, seconds - stepStart(i));
  }

  function togglePlay() {
    if (playing) {
      playing = false;
      cancelAnimationFrame(raf);
      raf = null;
      $("play").textContent = "▶ 播放";
      return;
    }
    if (index >= STEPS.length - 1 && elapsed >= stepDuration(index) - 0.01) {
      setStep(0, 0);
    }
    playing = true;
    lastTs = performance.now();
    $("play").textContent = "⏸ 暂停";
    raf = requestAnimationFrame(tick);
  }

  function tick(ts) {
    if (!playing) return;
    const dt = Math.max(0, (ts - lastTs) / 1000);
    lastTs = ts;
    elapsed += dt * speed;
    let duration = stepDuration(index);
    while (elapsed >= duration && index < STEPS.length - 1) {
      elapsed -= duration;
      index += 1;
      duration = stepDuration(index);
      render();
    }
    if (index >= STEPS.length - 1 && elapsed >= stepDuration(index)) {
      elapsed = stepDuration(index);
      playing = false;
      $("play").textContent = "▶ 播放";
      render();
      return;
    }
    render();
    raf = requestAnimationFrame(tick);
  }

  function buildChips() {
    $("chips").innerHTML = STEPS.map((step, i) =>
      `<button class="chip" data-step="${i}" title="${esc(step.description || "")}">${i + 1}. ${esc(step.type)}</button>`
    ).join("");
    document.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        playing = false;
        cancelAnimationFrame(raf);
        $("play").textContent = "▶ 播放";
        setStep(Number(chip.dataset.step), 0);
      });
    });
  }

  $("play").addEventListener("click", togglePlay);
  $("prev").addEventListener("click", () => { playing = false; cancelAnimationFrame(raf); $("play").textContent = "▶ 播放"; setStep(index - 1, 0); });
  $("next").addEventListener("click", () => { playing = false; cancelAnimationFrame(raf); $("play").textContent = "▶ 播放"; setStep(index + 1, 0); });
  $("reset").addEventListener("click", () => { playing = false; cancelAnimationFrame(raf); $("play").textContent = "▶ 播放"; setStep(0, 0); });
  $("speed").addEventListener("change", (e) => { speed = Number(e.target.value) || 1; });
  $("seek").addEventListener("input", (e) => {
    const wasPlaying = playing;
    playing = false;
    cancelAnimationFrame(raf);
    $("play").textContent = "▶ 播放";
    seekAbsolute((Number(e.target.value) / 1000) * TOTAL);
    if (wasPlaying) togglePlay();
  });
  document.addEventListener("keydown", (e) => {
    if (e.target && /INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return;
    if (e.code === "Space") { e.preventDefault(); togglePlay(); }
    else if (e.code === "ArrowLeft") { e.preventDefault(); playing = false; cancelAnimationFrame(raf); $("play").textContent = "▶ 播放"; setStep(index - 1, 0); }
    else if (e.code === "ArrowRight") { e.preventDefault(); playing = false; cancelAnimationFrame(raf); $("play").textContent = "▶ 播放"; setStep(index + 1, 0); }
    else if (e.code === "Home") { e.preventDefault(); setStep(0, 0); }
    else if (e.code === "End") { e.preventDefault(); setStep(STEPS.length - 1, 0); }
  });

  $("title").textContent = TRACE.metadata.title || "Two Sum · 交互式执行回放";
  $("subtitle").textContent = `真实执行轨迹 · ${STEPS.length} 个步骤 · 可任意跳转 · 完全离线`;
  $("trace-id").textContent = TRACE.metadata.execution_trace_id || "";
  $("verified").textContent = TRACE.verified ? "真实轨迹 · 已验证" : "未验证";
  buildChips();
  setStep(0, 0);
})();
</script>
</body>
</html>
"""
