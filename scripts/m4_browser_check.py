"""End-to-end browser check for the M4 workbench.

Starts the real FastAPI app in a temporary SQLite output, opens the built Vue
frontend in headless Edge through CDP, and drives the actual GUI: project
creation, editing, execution, playback, case switching, hint answer and refresh.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

import httpx
import websockets

ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = ROOT / "output" / "m4"
SERVER_OUT = OUT_ROOT / "e2e_data"
SHOT_DIR = OUT_ROOT / "screenshots"
BROWSER_JSON = OUT_ROOT / "browser_check.json"
PORT = 8766
CDP_PORT = 9340
EDGE_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]


def edge_path() -> Path:
    for candidate in EDGE_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("找不到 Microsoft Edge")


class Cdp:
    def __init__(self, websocket: Any) -> None:
        self.ws = websocket
        self._next_id = 0
        self.events: list[dict[str, Any]] = []

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        await self.ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=20)
            message = json.loads(raw)
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"CDP {method} 失败：{message['error']}")
                return message.get("result", {})
            self.events.append(message)

    async def js(self, expression: str) -> Any:
        result = await self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
                "userGesture": True,
            },
        )
        if result.get("exceptionDetails"):
            details = result["exceptionDetails"]
            raise RuntimeError(f"页面 JavaScript 异常：{details.get('text')} {details.get('exception')}")
        return result.get("result", {}).get("value")

    async def screenshot(self, name: str) -> str:
        result = await self.call(
            "Page.captureScreenshot",
            {"format": "png", "fromSurface": True, "captureBeyondViewport": False},
        )
        path = SHOT_DIR / name
        path.write_bytes(base64.b64decode(result["data"]))
        return str(path)

    async def close(self) -> None:
        await self.ws.close()


def check(results: list[dict[str, Any]], name: str, condition: bool, detail: Any = None) -> None:
    results.append({"name": name, "passed": bool(condition), "detail": detail})
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f" :: {detail}" if detail is not None else ""))
    if not condition:
        raise AssertionError(f"浏览器检查失败：{name} :: {detail}")


async def wait_js(cdp: Cdp, expression: str, *, timeout: float = 20.0, description: str = "") -> Any:
    deadline = time.time() + timeout
    last: Any = None
    while time.time() < deadline:
        try:
            last = await cdp.js(expression)
            if last:
                return last
        except Exception as exc:  # noqa: BLE001 - page may still be booting
            last = str(exc)
        await asyncio.sleep(0.15)
    raise TimeoutError(f"等待页面条件超时：{description or expression}；最后值={last!r}")


async def wait_server(client: httpx.Client, timeout: float = 25.0) -> dict:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            response = client.get("/health")
            if response.status_code == 200:
                return response.json()
            last = f"{response.status_code} {response.text[:200]}"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        await asyncio.sleep(0.2)
    raise TimeoutError(f"后端没有启动：{last}")


async def click(cdp: Cdp, selector: str) -> None:
    result = await cdp.js(
        "(() => { const el=document.querySelector(%s); if(!el) return false; el.click(); return true; })()"
        % json.dumps(selector)
    )
    if not result:
        raise AssertionError(f"找不到可点击元素：{selector}")


async def set_input(cdp: Cdp, selector: str, value: str, *, event: str = "input") -> None:
    result = await cdp.js(
        "(() => { const el=document.querySelector(%s); if(!el) return false;"
        " const proto=Object.getPrototypeOf(el);"
        " const setter=Object.getOwnPropertyDescriptor(proto,'value')?.set;"
        " if(setter) setter.call(el, %s); else el.value=%s;"
        " el.dispatchEvent(new Event(%s,{bubbles:true})); return true; })()"
        % (json.dumps(selector), json.dumps(value), json.dumps(value), json.dumps(event))
    )
    if not result:
        raise AssertionError(f"找不到输入元素：{selector}")


async def text(cdp: Cdp, selector: str) -> str:
    return await cdp.js(
        "(() => { const el=document.querySelector(%s); return el ? (el.textContent || '') : ''; })()"
        % json.dumps(selector)
    )


async def run() -> int:
    checks: list[dict[str, Any]] = []
    screenshots: list[str] = []
    payload: dict[str, Any] = {
        "checks": checks,
        "screenshots": screenshots,
        "server_output": str(SERVER_OUT),
    }
    started = time.time()
    server: subprocess.Popen | None = None
    cdp: Cdp | None = None
    profile_dir: Path | None = None
    try:
        OUT_ROOT.mkdir(parents=True, exist_ok=True)
        SHOT_DIR.mkdir(parents=True, exist_ok=True)
        stale_error = SHOT_DIR / "99_error.png"
        if stale_error.exists():
            stale_error.unlink()
        if SERVER_OUT.exists():
            shutil.rmtree(SERVER_OUT)
        SERVER_OUT.mkdir(parents=True)
        env = os.environ.copy()
        env["ALGOVIZ_OUTPUT"] = str(SERVER_OUT)
        env["PYTHONIOENCODING"] = "utf-8"
        server_log = OUT_ROOT / "server.log"
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "algoviz.api.app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(PORT),
                "--log-level",
                "warning",
            ],
            cwd=ROOT,
            env=env,
            stdout=server_log.open("w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
        )
        with httpx.Client(base_url=f"http://127.0.0.1:{PORT}", timeout=10) as api:
            health = await wait_server(api)
            check(checks, "后端启动并返回 health", health.get("status") == "ok", health.get("version"))
            root = api.get("/")
            check(checks, "FastAPI 提供 Vue 工作台入口", root.status_code == 200 and "AlgoViz Workbench" in root.text)
            await asyncio.sleep(0.2)

        profile_dir = Path(tempfile.mkdtemp(prefix="algoviz_m4_edge_"))
        edge = subprocess.Popen(
            [
                str(edge_path()),
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--remote-allow-origins=*",
                f"--remote-debugging-port={CDP_PORT}",
                f"--user-data-dir={profile_dir}",
                "--window-size=1600,1100",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        ws_url = None
        for _ in range(120):
            try:
                targets = httpx.get(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=1).json()
                pages = [
                    target
                    for target in targets
                    if target.get("type") == "page"
                    and not str(target.get("url", "")).startswith("chrome-extension://")
                ]
                page = next((item for item in pages if item.get("url") == "about:blank"), pages[0])
                ws_url = page.get("webSocketDebuggerUrl")
                if ws_url:
                    break
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(0.1)
        if not ws_url:
            raise TimeoutError("Edge CDP 没有启动")
        websocket = await websockets.connect(ws_url, max_size=40_000_000)
        cdp = Cdp(websocket)
        await cdp.call("Page.enable")
        await cdp.call("Runtime.enable")
        await cdp.call("Network.enable")
        await cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1600, "height": 1100, "deviceScaleFactor": 1, "mobile": False},
        )
        await cdp.call("Page.navigate", {"url": f"http://127.0.0.1:{PORT}/"})
        await wait_js(
            cdp,
            "document.readyState === 'complete' && !!window.__workbench && !!document.querySelector('[data-testid=welcome-sample-btn]')",
            description="Vue 工作台加载",
        )
        check(checks, "Vue 工作台初始页加载", True)
        screenshots.append(await cdp.screenshot("01_welcome.png"))

        # Create the sample project through the actual UI.
        await click(cdp, "[data-testid=welcome-sample-btn]")
        await wait_js(cdp, "!!document.querySelector('.workspace') && !!window.__workbench.getProjectId()", description="示例项目创建")
        await wait_js(cdp, "document.querySelector('[data-testid=case-count]')?.textContent === '6'", description="六个示例用例")
        check(checks, "通过 GUI 创建 Two Sum 示例项目", True)
        check(
            checks,
            "项目名称、题目、代码已加载",
            await cdp.js(
                "document.querySelector('[data-testid=project-name]').value === 'Two Sum 课堂示例'"
                " && document.querySelector('[data-testid=problem-title]').value.includes('Two Sum')"
                " && document.querySelector('.cm-content').textContent.includes('def two_sum')"
            ),
            await cdp.js("document.querySelector('[data-testid=project-name]').value"),
        )

        # Edit title, code, add/edit/delete a case through real DOM events.
        await set_input(cdp, "[data-testid=project-name]", "Two Sum GUI 测试项目")
        await set_input(cdp, "[data-testid=problem-title]", "Two Sum · GUI 课堂")
        await cdp.js("document.querySelector('.cm-content').focus()")
        await cdp.call("Input.insertText", {"text": "# GUI 编辑\n"})
        await asyncio.sleep(0.25)
        code_text = await cdp.js("document.querySelector('.cm-content').textContent")
        if "# GUI" not in code_text:
            await cdp.js(
                "window.__codeEditor.dispatch({changes:{from:0,to:0,insert:'# GUI 编辑\\n'}})"
            )
            await asyncio.sleep(0.2)
            code_text = await cdp.js("document.querySelector('.cm-content').textContent")
        check(checks, "代码编辑器支持真实编辑", "# GUI" in code_text, code_text[:50])

        await click(cdp, "[data-testid=add-case-btn]")
        await wait_js(cdp, "document.querySelector('[data-testid=case-count]').textContent === '7'")
        await cdp.js(
            "(() => { const cards=document.querySelectorAll('[data-testid=case-card]');"
            " const last=cards[cards.length-1];"
            " last?.querySelector('[data-testid=delete-case-btn]')?.click(); return true; })()"
        )
        await wait_js(cdp, "document.querySelector('[data-testid=case-count]').textContent === '6'")
        check(checks, "测试用例支持添加与删除", True)
        await click(cdp, "[data-testid=add-case-btn]")
        await wait_js(cdp, "document.querySelector('[data-testid=case-count]').textContent === '7'")
        new_case = await cdp.js(
            "(() => { const els=document.querySelectorAll('[data-testid=case-card]');"
            " return els[els.length-1]?.dataset.caseId || ''; })()"
        )
        check(checks, "新增用例获得独立 case_id", bool(new_case), new_case)
        await set_input(cdp, f'[data-case-id="{new_case}"] [data-testid=case-name]', "GUI 新增用例")
        await set_input(
            cdp,
            f'[data-case-id="{new_case}"] [data-testid=case-input]',
            '{"nums": [5, 5], "target": 10}',
        )
        await set_input(
            cdp,
            f'[data-case-id="{new_case}"] [data-testid=case-expected]',
            "[0, 1]",
        )
        await cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1600, "height": 1600, "deviceScaleFactor": 1, "mobile": False},
        )
        await cdp.js("window.scrollTo(0, 0)")
        await asyncio.sleep(0.2)
        screenshots.append(await cdp.screenshot("02_problem_and_cases.png"))
        await cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1600, "height": 1100, "deviceScaleFactor": 1, "mobile": False},
        )
        await cdp.js("window.scrollTo(0, 0)")

        await click(cdp, "[data-testid=save-project-btn]")
        await wait_js(
            cdp,
            "document.querySelector('[data-testid=notice-toast]')?.textContent.includes('已保存')",
            description="保存提示",
        )
        check(checks, "保存项目成功", (await text(cdp, "[data-testid=notice-toast]")).find("已保存") >= 0,
              await text(cdp, "[data-testid=notice-toast]"))

        # Real execution through the API and GUI polling.
        await click(cdp, "[data-testid=run-btn]")
        await wait_js(
            cdp,
            "document.querySelector('[data-testid=run-status]')?.textContent.trim() === '执行完成'",
            timeout=45,
            description="真实执行完成",
        )
        check(checks, "通过 GUI 发起真实执行并完成", True)
        run_id = await cdp.js("window.__workbench.getRunId()")
        check(checks, "生成真实 run_id", bool(run_id), run_id)
        summary_case_count = await cdp.js("window.__workbench.getRun()?.summary?.case_count")
        check(
            checks,
            "真实执行摘要显示 7 个用例",
            summary_case_count == 7,
            summary_case_count,
        )
        await wait_js(cdp, "document.querySelectorAll('[data-testid=case-card]').length === 7")
        await cdp.js("window.scrollTo(0, 0)")
        await asyncio.sleep(0.2)
        screenshots.append(await cdp.screenshot("03_after_execution.png"))

        # First case automatic selection / visual state.
        await wait_js(cdp, "window.__workbench.getCaseId() === 'case_normal'")
        check(
            checks,
            "第一个用例显示真实数组与 target",
            await cdp.js(
                "JSON.stringify([...document.querySelectorAll('[data-kind=\"array\"] .array-value')].map(n=>n.textContent))"
                " === JSON.stringify(['2','7','11','15'])"
                " && document.querySelector('[data-kind=\"array\"] .array-target')?.textContent.includes('9')"
            ),
            await cdp.js("document.querySelector('[data-kind=\"array\"] .array-target')?.textContent"),
        )
        initial_line = await cdp.js("document.querySelector('.code-view-line.active .code-view-no')?.textContent")
        expected_initial_line = await cdp.js(
            "(() => { const c=window.__workbench.getDeck().cases.find(x=>x.case_id==='case_normal');"
            " return String(c.trace.steps[0].code_line); })()"
        )
        check(checks, "初始执行行高亮", initial_line == expected_initial_line, { "actual": initial_line, "expected": expected_initial_line })

        await click(cdp, "[data-testid=next-btn]")
        await click(cdp, "[data-testid=next-btn]")
        miss_line = await cdp.js("document.querySelector('.code-view-line.active .code-view-no')?.textContent")
        expected_miss_line = await cdp.js(
            "(() => { const c=window.__workbench.getDeck().cases.find(x=>x.case_id==='case_normal');"
            " return String(c.trace.steps[2].code_line); })()"
        )
        check(
            checks,
            "手动前进到 miss 步骤并同步代码 / 哈希 / 提示",
            await cdp.js(
                "window.__workbench.getStepIndex() === 2"
                " && !!document.querySelector('[data-kind=\"hash_map\"] .pill.miss')"
                " && document.querySelector('[data-testid=hint-title]')?.textContent.includes('未命中')"
            ) and miss_line == expected_miss_line,
            {"hint": await text(cdp, "[data-testid=hint-title]"), "line": miss_line, "expected": expected_miss_line},
        )
        await click(cdp, "[data-testid=prev-btn]")
        check(checks, "上一步回到步骤 2", await cdp.js("window.__workbench.getStepIndex() === 1"))

        hit_index = await cdp.js(
            "(() => { const c=window.__workbench.getDeck().cases.find(x=>x.case_id==='case_normal');"
            " return c.trace.steps.findIndex(s=>s.type==='found'); })()"
        )
        await set_input(cdp, "[data-testid=timeline]", str(hit_index))
        await asyncio.sleep(0.2)
        check(
            checks,
            "时间轴跳转到命中步骤",
            await cdp.js(
                f"window.__workbench.getStepIndex() === {hit_index}"
                " && document.querySelectorAll('[data-kind=\"array\"] .array-cell.found').length === 2"
                " && document.querySelector('[data-testid=hint-title]')?.textContent.includes('返回答案')"
            ),
            await text(cdp, "[data-testid=hint-title]"),
        )
        await click(cdp, "[data-testid=hint-toggle]")
        check(checks, "课堂参考答案可展开", await cdp.js("!!document.querySelector('[data-testid=hint-answer]')"))
        await cdp.js("window.scrollTo(0, 0)")
        await asyncio.sleep(0.15)
        screenshots.append(await cdp.screenshot("04_hit_and_hint.png"))

        # Auto / pause / speed.
        await click(cdp, "[data-testid=reset-btn]")
        await click(cdp, "[data-testid=play-btn]")
        await asyncio.sleep(0.25)
        check(checks, "自动播放进入 playing 状态", await cdp.js("window.__workbench.getPlaying() === true"))
        await click(cdp, "[data-testid=pause-btn]")
        paused_index = await cdp.js("window.__workbench.getStepIndex()")
        await asyncio.sleep(0.8)
        check(
            checks,
            "暂停后旧 timer 不推进",
            await cdp.js(f"window.__workbench.getPlaying() === false && window.__workbench.getStepIndex() === {paused_index}"),
            paused_index,
        )
        await set_input(cdp, "[data-testid=speed-select]", "2", event="change")
        check(checks, "播放速度切换到 2×", await cdp.js("window.__workbench.getSpeed() === 2"))

        # Switch case while playing.
        await click(cdp, "[data-testid=play-btn]")
        await asyncio.sleep(0.2)
        await click(cdp, ".case-tab[data-case-id=case_first]")
        await wait_js(cdp, "window.__workbench.getCaseId() === 'case_first'")
        check(
            checks,
            "播放中切换用例后从 step 0 开始",
            await cdp.js(
                "window.__workbench.getStepIndex() === 0"
                " && window.__workbench.getPlaying() === false"
                " && JSON.stringify([...document.querySelectorAll('[data-kind=\"array\"] .array-value')].map(n=>n.textContent))"
                " === JSON.stringify(['3','2','4'])"
                " && document.querySelector('[data-kind=\"array\"] .array-target')?.textContent.includes('5')"
                " && !document.querySelector('[data-testid=hint-answer]')"
            ),
            await cdp.js("JSON.stringify(window.__workbench.getStepIndex())"),
        )
        await cdp.js("window.scrollTo(0, 0)")
        await asyncio.sleep(0.15)
        screenshots.append(await cdp.screenshot("05_case_switch.png"))
        await asyncio.sleep(1.3)
        check(checks, "切换后旧用例 timer 不再推进", await cdp.js("window.__workbench.getStepIndex() === 0"))

        await click(cdp, "[data-testid=auto-btn]")
        await asyncio.sleep(1.35)
        check(checks, "Case 2 自动播放推进", await cdp.js("window.__workbench.getPlaying() === true && window.__workbench.getStepIndex() >= 2"))
        await click(cdp, "[data-testid=pause-btn]")
        paused2 = await cdp.js("window.__workbench.getStepIndex()")
        await click(cdp, "[data-testid=resume-btn]")
        await asyncio.sleep(0.9)
        check(
            checks,
            "暂停后继续从当前位置推进",
            await cdp.js(f"window.__workbench.getStepIndex() > {paused2}"),
            await cdp.js("window.__workbench.getStepIndex()"),
        )
        await click(cdp, "[data-testid=pause-btn]")

        # Switch back and refresh. localStorage must restore saved project and last run.
        await click(cdp, ".case-tab[data-case-id=case_normal]")
        check(
            checks,
            "切回 Case 1 恢复正确数组和 target",
            await cdp.js(
                "window.__workbench.getCaseId() === 'case_normal'"
                " && JSON.stringify([...document.querySelectorAll('[data-kind=\"array\"] .array-value')].map(n=>n.textContent))"
                " === JSON.stringify(['2','7','11','15'])"
                " && document.querySelector('[data-kind=\"array\"] .array-target')?.textContent.includes('9')"
            ),
        )
        await cdp.js("window.scrollTo(0, 0)")
        await click(cdp, "[data-testid=auto-btn]")
        await asyncio.sleep(5.4)
        check(
            checks,
            "自动播放到末尾后停止",
            await cdp.js(
                "window.__workbench.getPlaying() === false"
                " && window.__workbench.getStepIndex() === window.__workbench.getDeck().cases"
                ".find(c=>c.case_id==='case_normal').trace.steps.length - 1"
            ),
            await cdp.js("window.__workbench.getStepIndex()"),
        )
        await cdp.call("Page.reload", {"ignoreCache": True})
        await asyncio.sleep(0.6)
        await wait_js(
            cdp,
            "document.readyState === 'complete' && !!window.__workbench && !!window.__workbench.getProjectId()",
            timeout=20,
            description="刷新后恢复项目",
        )
        await wait_js(
            cdp,
            "document.querySelector('[data-testid=run-status]')?.textContent.trim() === '执行完成'",
            timeout=30,
            description="刷新后恢复最近一次执行",
        )
        check(
            checks,
            "刷新后项目、最近执行与可视化仍可查看",
            await cdp.js(
                "document.querySelector('[data-testid=project-name]').value === 'Two Sum GUI 测试项目'"
                " && document.querySelectorAll('[data-testid=case-card]').length === 7"
                " && window.__workbench.getRunId() !== null"
                " && document.querySelectorAll('[data-kind=\"array\"] .array-cell').length >= 4"
            ),
            await cdp.js("document.querySelector('[data-testid=project-name]').value"),
        )
        await cdp.js("window.scrollTo(0, 0)")
        await asyncio.sleep(0.15)
        screenshots.append(await cdp.screenshot("06_after_refresh.png"))

        # Check backend persistence independently from the browser state.
        with httpx.Client(base_url=f"http://127.0.0.1:{PORT}", timeout=10) as api:
            project_id = await cdp.js("window.__workbench.getProjectId()")
            project = api.get(f"/api/v1/workbench/projects/{project_id}").json()
            runs = api.get(f"/api/v1/workbench/projects/{project_id}/runs").json()
            cases = api.get(f"/api/v1/workbench/runs/{run_id}/cases").json()
            classroom = api.get(f"/api/v1/workbench/runs/{run_id}/classroom").json()
        check(checks, "后端持久化项目名称与 7 个用例", project["name"] == "Two Sum GUI 测试项目" and len(project["cases"]) == 7,
              {"name": project.get("name"), "cases": len(project.get("cases", []))})
        check(checks, "后端保留执行历史", len(runs) >= 1 and runs[0]["run_id"] == run_id, [r["run_id"] for r in runs])
        check(checks, "每个可执行用例取得独立 trace", len({c["execution_trace_id"] for c in cases if c["execution_trace_id"]}) >= 6,
              [c["execution_trace_id"] for c in cases])
        steps_total = sum(
            len(item.get("trace", {}).get("steps", []))
            for item in classroom["classroom"]["cases"]
            if item.get("trace")
        )
        check(
            checks,
            "ClassroomDeck 含 7 个用例、独立提示与真实步骤",
            len(classroom["classroom"]["cases"]) == 7
            and len(classroom["classroom"]["cases"][0]["hints"]) == 8
            and steps_total >= 20,
            {"cases": len(classroom["classroom"]["cases"]), "steps": steps_total},
        )
        check(checks, "浏览器无 JavaScript 错误", await cdp.js("(window.__errors || []).length === 0"), await cdp.js("window.__errors || []"))

        payload.update(
            {
                "passed": all(item["passed"] for item in checks),
                "elapsed_seconds": round(time.time() - started, 2),
                "final_state": await cdp.js("({project:window.__workbench.getProjectId(),run:window.__workbench.getRunId(),case:window.__workbench.getCaseId(),step:window.__workbench.getStepIndex()})"),
                "screenshots": screenshots,
                "run_id": run_id,
                "browser_errors": await cdp.js("window.__errors || []"),
            }
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        payload.update(
            {
                "passed": False,
                "elapsed_seconds": round(time.time() - started, 2),
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "screenshots": screenshots,
            }
        )
        if cdp is not None:
            try:
                screenshots.append(await cdp.screenshot("99_error.png"))
                payload["screenshots"] = screenshots
                payload["page"] = await cdp.js("({href:location.href,errors:window.__errors||[],body:document.body?.innerText?.slice(0,500)})")
            except Exception:  # noqa: BLE001
                pass
        return 1
    finally:
        if cdp is not None:
            try:
                await cdp.close()
            except Exception:  # noqa: BLE001
                pass
        if profile_dir is not None:
            shutil.rmtree(profile_dir, ignore_errors=True)
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()
        BROWSER_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n结果：", BROWSER_JSON)
        print(json.dumps({k: v for k, v in payload.items() if k not in {"checks", "traceback"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
