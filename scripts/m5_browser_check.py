"""M5 real-browser E2E: Binary Search + Two Sum regression.

Starts the real FastAPI app with isolated SQLite output, drives the built Vue
workbench in headless Edge through CDP, and verifies the second algorithm's
dynamic VisualPlan, execution, playback, hints, case switching and refresh.
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
OUT_ROOT = ROOT / "output" / "m5"
SERVER_OUT = OUT_ROOT / "e2e_data"
SHOT_DIR = OUT_ROOT / "screenshots"
BROWSER_JSON = OUT_ROOT / "browser_check.json"
PORT = 8767
CDP_PORT = 9341
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
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f" :: {detail}" if detail is not None else ""))
    if not condition:
        raise AssertionError(f"浏览器检查失败：{name} :: {detail}")


async def wait_js(cdp: Cdp, expression: str, *, timeout: float = 25.0, description: str = "") -> Any:
    deadline = time.time() + timeout
    last: Any = None
    while time.time() < deadline:
        try:
            last = await cdp.js(expression)
            if last:
                return last
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        await asyncio.sleep(0.15)
    raise TimeoutError(f"等待页面条件超时：{description or expression}；最后值={last!r}")


async def wait_server(client: httpx.Client, timeout: float = 30.0) -> dict:
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
    ok = await cdp.js(
        "(() => { const el=document.querySelector(%s); if(!el) return false; el.click(); return true; })()"
        % json.dumps(selector)
    )
    if not ok:
        raise AssertionError(f"找不到可点击元素：{selector}")


async def set_input(cdp: Cdp, selector: str, value: str, *, event: str = "input") -> None:
    ok = await cdp.js(
        "(() => { const el=document.querySelector(%s); if(!el) return false;"
        " const proto=Object.getPrototypeOf(el);"
        " const setter=Object.getOwnPropertyDescriptor(proto,'value')?.set;"
        " if(setter) setter.call(el, %s); else el.value=%s;"
        " el.dispatchEvent(new Event(%s,{bubbles:true})); return true; })()"
        % (json.dumps(selector), json.dumps(value), json.dumps(value), json.dumps(event))
    )
    if not ok:
        raise AssertionError(f"找不到输入元素：{selector}")


async def text(cdp: Cdp, selector: str) -> str:
    return await cdp.js(
        "(() => { const el=document.querySelector(%s); return el ? (el.textContent || '') : ''; })()"
        % json.dumps(selector)
    )


async def run() -> int:
    results: list[dict[str, Any]] = []
    screenshots: list[str] = []
    payload: dict[str, Any] = {
        "checks": results,
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
        stale = SHOT_DIR / "99_error.png"
        if stale.exists():
            stale.unlink()
        if SERVER_OUT.exists():
            shutil.rmtree(SERVER_OUT)
        SERVER_OUT.mkdir(parents=True)
        env = os.environ.copy()
        env["ALGOVIZ_OUTPUT"] = str(SERVER_OUT)
        env["PYTHONIOENCODING"] = "utf-8"
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
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with httpx.Client(base_url=f"http://127.0.0.1:{PORT}", timeout=10) as api:
            health = await wait_server(api)
            check(results, "后端启动并返回 health", health.get("status") == "ok", health.get("version"))
            root = api.get("/")
            check(results, "FastAPI 提供 Vue 工作台入口", root.status_code == 200 and "AlgoViz Workbench" in root.text)

        profile_dir = Path(tempfile.mkdtemp(prefix="algoviz_m5_edge_"))
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
                    item
                    for item in targets
                    if item.get("type") == "page"
                    and not str(item.get("url", "")).startswith("chrome-extension://")
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
            "document.readyState === 'complete' && !!window.__workbench && !!document.querySelector('[data-testid=welcome-binary-btn]')",
            description="Vue 工作台加载",
        )
        check(results, "Vue 工作台初始页加载", True)

        # 1. Create binary search project through the GUI.
        await click(cdp, "[data-testid=welcome-binary-btn]")
        await wait_js(cdp, "!!window.__workbench.getProjectId() && document.querySelector('[data-testid=case-count]')?.textContent === '6'")
        check(
            results,
            "GUI 创建二分查找项目",
            await cdp.js(
                "document.querySelector('[data-testid=problem-algorithm]').value === 'binary_search'"
                " && document.querySelector('[data-testid=problem-title]').value.includes('Binary Search')"
                " && document.querySelector('.cm-content').textContent.includes('def binary_search')"
            ),
            await cdp.js("document.querySelector('[data-testid=problem-algorithm]').value"),
        )
        check(results, "二分查找示例包含 6 个用例", await cdp.js("document.querySelector('[data-testid=case-count]').textContent === '6'"))
        screenshots.append(await cdp.screenshot("01_binary_project.png"))

        # 2. Edit project title, code (real CodeMirror input), and save.
        await set_input(cdp, "[data-testid=project-name]", "M5 二分查找 GUI")
        await cdp.js("document.querySelector('.cm-content').focus()")
        await cdp.call("Input.insertText", {"text": "# M5 GUI 编辑\n"})
        await asyncio.sleep(0.25)
        await click(cdp, "[data-testid=save-project-btn]")
        await wait_js(
            cdp,
            "document.querySelector('[data-testid=notice-toast]')?.textContent.includes('已保存')",
            description="保存二分查找项目",
        )
        check(results, "二分查找源码可编辑并保存", True)

        # 3. Run through the GUI and wait for real backend execution.
        await click(cdp, "[data-testid=run-btn]")
        await wait_js(
            cdp,
            "document.querySelector('[data-testid=run-status]')?.textContent.trim() === '执行完成'",
            timeout=45,
            description="二分查找真实执行完成",
        )
        run_id = await cdp.js("window.__workbench.getRunId()")
        summary_case_count = await cdp.js("window.__workbench.getRun()?.summary?.case_count")
        summary_success = await cdp.js("window.__workbench.getRun()?.summary?.success")
        summary_failed = await cdp.js("window.__workbench.getRun()?.summary?.failed")
        check(results, "二分查找真实执行完成", bool(run_id) and summary_case_count == 6, {"run_id": run_id, "cases": summary_case_count})
        check(results, "二分查找 6 个用例全部成功", summary_success == 6 and summary_failed == 0, {"success": summary_success, "failed": summary_failed})
        await wait_js(cdp, "window.__workbench.getCaseId() === 'bs_middle'")

        # 4. Dynamic VisualPlan: search_range exists; hash_map is absent.
        check(
            results,
            "VisualPlan 动态装配二分查找组件",
            await cdp.js(
                "!!document.querySelector('.visual-component[data-kind=\"array\"]')"
                " && !!document.querySelector('.visual-component[data-kind=\"search_range\"]')"
                " && !!document.querySelector('.visual-component[data-kind=\"variables\"]')"
                " && !!document.querySelector('.visual-component[data-kind=\"code\"]')"
                " && !document.querySelector('.visual-component[data-kind=\"hash_map\"]')"
            ),
            await cdp.js("[...document.querySelectorAll('.visual-component')].map(el=>el.dataset.kind)"),
        )
        check(
            results,
            "二分查找数组、区间和提示同步",
            await cdp.js(
                "JSON.stringify([...document.querySelectorAll('.array-cell .array-value')].map(n=>n.textContent))"
                " === JSON.stringify(['1','3','5','7','9','11'])"
                " && document.querySelector('[data-testid=search-range-label]')?.textContent.includes('[0, 5]')"
                " && document.querySelector('[data-testid=hint-title]')?.textContent.includes('初始化搜索区间')"
            ),
            await text(cdp, "[data-testid=hint-title]"),
        )
        expected_binary_line = await cdp.js(
            "(() => { const c=window.__workbench.getDeck().cases.find(x=>x.case_id==='bs_middle');"
            " return String(c.trace.steps[0].code_line); })()"
        )
        check(
            results,
            "二分查找当前代码行高亮",
            await cdp.js("document.querySelector('.code-view-line.active .code-view-no')?.textContent") == expected_binary_line,
            {"actual": await cdp.js("document.querySelector('.code-view-line.active .code-view-no')?.textContent"), "expected": expected_binary_line},
        )
        screenshots.append(await cdp.screenshot("02_binary_execution.png"))

        # Registry fallback: inject an unknown kind into the client-side plan copy.
        await cdp.js(
            "(() => { const d=window.__workbench.getDeck();"
            " d.visual_plan.components.push({component_id:'unknown_demo',kind:'unknown_demo_kind',"
            " slot:'array',title:'未知组件测试',options:{title:'未知组件测试'}}); return true; })()"
        )
        await wait_js(cdp, "!!document.querySelector('[data-testid=unknown-component]')", description="未知组件错误态")
        unknown_text = await text(cdp, "[data-testid=unknown-component]")
        check(
            results,
            "未知 VisualPlan 组件显示明确错误态",
            "unknown_demo_kind" in unknown_text,
            unknown_text,
        )
        screenshots.append(await cdp.screenshot("07_unknown_component.png"))
        await cdp.js("window.__workbench.getDeck().visual_plan.components.pop()")
        await asyncio.sleep(0.15)

        # 5. Manual step to mid, timeline jump to found, hint answer.
        await click(cdp, "[data-testid=next-btn]")
        check(
            results,
            "二分查找下一步显示 mid 与搜索区间",
            await cdp.js(
                "window.__workbench.getStepIndex() === 1"
                " && document.querySelector('[data-testid=search-range-label]')?.textContent.includes('[0, 5]')"
                " && document.querySelector('.range-pointer.mid b')?.textContent === '2'"
                " && document.querySelector('[data-testid=hint-title]')?.textContent.includes('计算中点')"
            ),
            await cdp.js("document.querySelector('.range-pointer.mid b')?.textContent"),
        )
        await click(cdp, "[data-testid=prev-btn]")
        check(
            results,
            "二分查找上一步回到初始化步骤",
            await cdp.js("window.__workbench.getStepIndex() === 0 && document.querySelector('[data-testid=hint-title]')?.textContent.includes('初始化搜索区间')"),
        )
        found_index = await cdp.js(
            "(() => { const c=window.__workbench.getDeck().cases.find(x=>x.case_id==='bs_middle');"
            " return c.trace.steps.findIndex(s=>s.type==='found'); })()"
        )
        await set_input(cdp, "[data-testid=timeline]", str(found_index))
        await asyncio.sleep(0.2)
        check(
            results,
            "时间轴跳到二分查找命中步骤",
            await cdp.js(
                f"window.__workbench.getStepIndex() === {found_index}"
                " && document.querySelectorAll('.visual-component[data-kind=\"array\"] .array-cell.found').length === 1"
                " && document.querySelector('[data-testid=hint-title]')?.textContent.includes('找到目标')"
            ),
            await text(cdp, "[data-testid=hint-title]"),
        )
        await click(cdp, "[data-testid=hint-toggle]")
        check(results, "二分查找课堂参考答案可展开", await cdp.js("!!document.querySelector('[data-testid=hint-answer]')"))
        screenshots.append(await cdp.screenshot("03_binary_hint.png"))

        # 6. Auto play, pause, speed, switch case while playing.
        await click(cdp, "[data-testid=reset-btn]")
        await click(cdp, "[data-testid=play-btn]")
        await asyncio.sleep(1.35)
        check(
            results,
            "二分查找自动播放推进步骤",
            await cdp.js("window.__workbench.getPlaying() === true && window.__workbench.getStepIndex() >= 1"),
            await cdp.js("window.__workbench.getStepIndex()"),
        )
        await click(cdp, "[data-testid=pause-btn]")
        paused = await cdp.js("window.__workbench.getStepIndex()")
        await asyncio.sleep(0.7)
        check(
            results,
            "二分查找暂停后旧 timer 不推进",
            await cdp.js(f"window.__workbench.getPlaying() === false && window.__workbench.getStepIndex() === {paused}"),
        )
        await click(cdp, "[data-testid=resume-btn]")
        await asyncio.sleep(1.4)
        check(
            results,
            "二分查找继续后从暂停位置推进",
            await cdp.js(f"window.__workbench.getPlaying() === true && window.__workbench.getStepIndex() > {paused}"),
            await cdp.js("window.__workbench.getStepIndex()"),
        )
        await click(cdp, "[data-testid=pause-btn]")
        await set_input(cdp, "[data-testid=speed-select]", "2", event="change")
        check(results, "二分查找速度切换为 2×", await cdp.js("window.__workbench.getSpeed() === 2"))
        await click(cdp, "[data-testid=play-btn]")
        await asyncio.sleep(0.2)
        await click(cdp, ".case-tab[data-case-id=bs_none]")
        await wait_js(cdp, "window.__workbench.getCaseId() === 'bs_none'")
        check(
            results,
            "播放中切换二分查找用例后从 step 0 开始",
            await cdp.js(
                "window.__workbench.getStepIndex() === 0"
                " && window.__workbench.getPlaying() === false"
                " && document.querySelector('[data-testid=search-range-label]')?.textContent.includes('[0, 5]')"
                " && document.querySelector('[data-testid=hint-title]')?.textContent.includes('初始化搜索区间')"
            ),
        )
        screenshots.append(await cdp.screenshot("04_binary_case_switch.png"))
        await asyncio.sleep(1.2)
        check(results, "二分查找切换用例后旧 timer 不推进", await cdp.js("window.__workbench.getStepIndex() === 0"))

        # 7. Refresh and restore current binary run.
        await cdp.call("Page.reload", {"ignoreCache": True})
        await asyncio.sleep(0.6)
        await wait_js(
            cdp,
            "document.readyState === 'complete' && !!window.__workbench.getProjectId() && !!window.__workbench.getRunId()",
            timeout=30,
            description="二分查找刷新恢复",
        )
        await wait_js(
            cdp,
            "document.querySelector('[data-testid=run-status]')?.textContent.trim() === '执行完成'",
            timeout=30,
            description="二分查找刷新恢复最近 run",
        )
        check(
            results,
            "刷新后二分查找项目、轨迹和动态组件恢复",
            await cdp.js(
                "document.querySelector('[data-testid=project-name]').value === 'M5 二分查找 GUI'"
                " && document.querySelector('[data-testid=problem-algorithm]').value === 'binary_search'"
                " && !!document.querySelector('.visual-component[data-kind=\"search_range\"]')"
                " && !!window.__workbench.getRunId()"
            ),
        )
        screenshots.append(await cdp.screenshot("05_binary_after_refresh.png"))

        # 8. Return to Two Sum through the GUI and confirm the old component set.
        previous_project = await cdp.js("window.__workbench.getProjectId()")
        await click(cdp, "[data-testid=new-project-btn]")
        await wait_js(
            cdp,
            "window.__workbench.getProjectId() && window.__workbench.getProjectId() !== %s"
            % json.dumps(previous_project),
            description="新项目创建完成",
        )
        await wait_js(
            cdp,
            "document.querySelector('[data-testid=project-name]')?.value === '新算法项目'",
            description="新项目表单加载",
        )
        await click(cdp, "[data-testid=fill-sample-btn]")
        await wait_js(
            cdp,
            "document.querySelector('[data-testid=problem-algorithm]')?.value === 'two_sum'"
            " && document.querySelector('[data-testid=case-count]')?.textContent === '6'",
            description="填入 Two Sum 示例",
        )
        await click(cdp, "[data-testid=save-project-btn]")
        await wait_js(
            cdp,
            "document.querySelector('[data-testid=notice-toast]')?.textContent.includes('已保存')",
            description="保存 Two Sum 回归项目",
        )
        await click(cdp, "[data-testid=run-btn]")
        await wait_js(
            cdp,
            "document.querySelector('[data-testid=run-status]')?.textContent.trim() === '执行完成'",
            timeout=45,
            description="Two Sum 回归执行完成",
        )
        check(
            results,
            "回到 Two Sum 后仍使用 hash_map 组件而非 search_range",
            await cdp.js(
                "document.querySelector('[data-testid=problem-algorithm]').value === 'two_sum'"
                " && !!document.querySelector('.visual-component[data-kind=\"hash_map\"]')"
                " && !document.querySelector('.visual-component[data-kind=\"search_range\"]')"
                " && JSON.stringify([...document.querySelectorAll('.array-cell .array-value')].map(n=>n.textContent))"
                " === JSON.stringify(['2','7','11','15'])"
            ),
        )
        screenshots.append(await cdp.screenshot("06_two_sum_regression.png"))

        # 9. Backend persistence/API verification.
        with httpx.Client(base_url=f"http://127.0.0.1:{PORT}", timeout=10) as api:
            projects = api.get("/api/v1/workbench/projects").json()
            binary_project = next((item for item in projects if item["name"] == "M5 二分查找 GUI"), None)
            binary_run = api.get(f"/api/v1/workbench/runs/{run_id}").json()
            binary_cases = api.get(f"/api/v1/workbench/runs/{run_id}/cases").json()
            binary_classroom = api.get(f"/api/v1/workbench/runs/{run_id}/classroom").json()["classroom"]
        check(results, "后端持久化至少两个算法项目", len(projects) >= 2 and binary_project is not None, [item["name"] for item in projects])
        check(
            results,
            "二分查找后端 Run / CaseRun / ClassroomDeck 完整",
            binary_run["status"] == "completed"
            and len(binary_cases) == 6
            and len({item["execution_trace_id"] for item in binary_cases}) == 6
            and [item["kind"] for item in binary_classroom["visual_plan"]["components"]]
            == ["array", "search_range", "variables", "code"],
            {"run": binary_run["run_id"], "cases": len(binary_cases)},
        )
        check(results, "浏览器无 JavaScript 错误", await cdp.js("(window.__errors || []).length === 0"), await cdp.js("window.__errors || []"))

        payload.update(
            {
                "passed": all(item["passed"] for item in results),
                "elapsed_seconds": round(time.time() - started, 2),
                "screenshots": screenshots,
                "binary_run_id": run_id,
                "final_state": await cdp.js("({project:window.__workbench.getProjectId(),run:window.__workbench.getRunId(),case:window.__workbench.getCaseId()})"),
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
                payload["page"] = await cdp.js("({href:location.href,errors:window.__errors||[],body:document.body?.innerText?.slice(0,700)})")
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
