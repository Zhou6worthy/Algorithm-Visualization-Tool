"""用真实 headless Edge + CDP 验证课堂 HTML 的交互行为。

不是检查按钮字符串是否存在，而是点击按钮、拖动时间轴、切换用例、自动播放，
并从 DOM 和控制器的真实状态读取结果。
"""
from __future__ import annotations

import asyncio
import base64
import json
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
HTML_PATH = ROOT / "output" / "m3_8" / "classroom.html"
OUT_DIR = ROOT / "output" / "m3_8"
SHOT_DIR = OUT_DIR / "screenshots"
EDGE_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]
PORT = 9339


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
            raw = await asyncio.wait_for(self.ws.recv(), timeout=15)
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
        value = result.get("result", {})
        return value.get("value")

    async def screenshot(self, name: str) -> str:
        result = await self.call(
            "Page.captureScreenshot",
            {"format": "png", "fromSurface": True, "captureBeyondViewport": False},
        )
        SHOT_DIR.mkdir(parents=True, exist_ok=True)
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


async def wait_ready(cdp: Cdp) -> None:
    for _ in range(120):
        value = await cdp.js("document.readyState + '|' + String(window.__classroomReady === true)")
        if value == "complete|true":
            return
        await asyncio.sleep(0.1)
    raise TimeoutError(
        "页面没有在 12 秒内就绪；"
        + json.dumps(
            {
                "state": await cdp.js("document.readyState"),
                "href": await cdp.js("location.href"),
                "title": await cdp.js("document.title"),
                "body": (await cdp.js("document.body ? document.body.innerText.slice(0, 500) : 'no body'")),
                "errors": await cdp.js("window.__classroomErrors || []"),
                "exception_events": [
                    event for event in cdp.events if event.get("method") == "Runtime.exceptionThrown"
                ][-5:],
            },
            ensure_ascii=False,
        )
    )


async def run() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    if not HTML_PATH.exists():
        raise FileNotFoundError(f"缺少课堂 HTML：{HTML_PATH}")

    profile_dir = Path(tempfile.mkdtemp(prefix="algoviz_m3_8_edge_"))
    proc = subprocess.Popen(
        [
            str(edge_path()),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--allow-file-access-from-files",
            "--remote-allow-origins=*",
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={profile_dir}",
            "--window-size=1600,1100",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    results: list[dict[str, Any]] = []
    screenshots: list[str] = []
    payload: dict[str, Any] = {
        "browser": str(edge_path()),
        "html": str(HTML_PATH),
        "checks": results,
        "screenshots": screenshots,
    }
    started = time.time()
    cdp: Cdp | None = None
    try:
        ws_url = None
        for _ in range(100):
            try:
                targets = httpx.get(f"http://127.0.0.1:{PORT}/json/list", timeout=1).json()
                pages = [
                    target
                    for target in targets
                    if target.get("type") == "page"
                    and not str(target.get("url", "")).startswith("chrome-extension://")
                ]
                page = next((target for target in pages if target.get("url") == "about:blank"), pages[0])
                ws_url = page.get("webSocketDebuggerUrl")
                if ws_url:
                    break
            except Exception:  # noqa: BLE001 - 浏览器启动期允许重试
                pass
            await asyncio.sleep(0.1)
        if not ws_url:
            raise TimeoutError("Edge CDP 没有启动")
        websocket = await websockets.connect(ws_url, max_size=30_000_000)
        cdp = Cdp(websocket)
        await cdp.call("Page.enable")
        await cdp.call("Runtime.enable")
        await cdp.call("Network.enable")
        await cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1600, "height": 1100, "deviceScaleFactor": 1, "mobile": False},
        )
        await cdp.call("Page.navigate", {"url": HTML_PATH.resolve().as_uri()})
        await wait_ready(cdp)

        check(results, "页面加载完成且无 JavaScript 错误", not (await cdp.js("window.__classroomErrors || []")),
              await cdp.js("window.__classroomErrors || []"))
        title_count = await cdp.js(
            "document.querySelector('#deck-title').textContent + '|' + document.querySelectorAll('.case-card').length"
        )
        check(results, "标题和用例数量", title_count == "Two Sum · 哈希表课堂演示|10", title_count)
        check(results, "默认选中 normal 用例",
              await cdp.js("window.__classroom.getState().caseId === 'normal' && document.querySelector('#current-case-name').textContent === '正常查找'"),
              await cdp.js("document.querySelector('#current-case-name').textContent"))
        check(results, "初始数组和目标值",
              await cdp.js("JSON.stringify([...document.querySelectorAll('[data-component-id=\"array\"] .cell:not([hidden]) .value')].map(n=>n.textContent)) === JSON.stringify(['2','7','11','15']) && document.querySelector('[data-component-id=\"array\"] .array-target').textContent.includes('9')"),
              await cdp.js("document.querySelector('[data-component-id=\"array\"] .array-target').textContent"))
        active_line = await cdp.js(
            "document.querySelector('.code-line.active .no') && document.querySelector('.code-line.active .no').textContent"
        )
        check(results, "初始代码高亮在第 2 行", active_line == "2", active_line)
        check(results, "初始教学提示为初始化",
              await cdp.js("document.querySelector('#hint-title').textContent.includes('初始化')"),
              await cdp.js("document.querySelector('#hint-title').textContent"))

        # 手动下一步两次：停在 miss 查询步骤。
        await cdp.js("document.querySelector('#next').click()")
        await cdp.js("document.querySelector('#next').click()")
        check(results, "手动下一步到步骤 3/8",
              await cdp.js("window.__classroom.getState().index === 2 && document.querySelector('#progress-label').textContent.includes('3 / 8')"),
              await cdp.js("document.querySelector('#progress-label').textContent"))
        miss_detail = await cdp.js(
            "JSON.stringify({active:!!document.querySelector('[data-component-id=\"array\"] .cell.active'), miss:!!document.querySelector('[data-component-id=\"hash_map\"] .pill.miss'), hint:document.querySelector('#hint-title').textContent})"
        )
        check(results, "查询 miss 的数组指针和哈希提示",
              await cdp.js("!!document.querySelector('[data-component-id=\"array\"] .cell.active') && !!document.querySelector('[data-component-id=\"hash_map\"] .pill.miss') && document.querySelector('#hint-title').textContent.includes('未命中')"),
              miss_detail)
        screenshots.append(await cdp.screenshot("01_normal_miss.png"))

        # 上一步与时间轴跳转。
        await cdp.js("document.querySelector('#prev').click()")
        check(results, "上一步回到步骤 2/8",
              await cdp.js("window.__classroom.getState().index === 1 && document.querySelector('#progress-label').textContent.includes('2 / 8')"),
              await cdp.js("document.querySelector('#progress-label').textContent"))
        hit_index = await cdp.js(
            "window.__classroom.deck.cases.find(c=>c.case_id==='normal').trace.steps.findIndex(s=>s.type==='found')"
        )
        await cdp.js(
            "(() => { const el=document.querySelector('#seek'); el.value='%d'; el.dispatchEvent(new Event('input',{bubbles:true})); return el.value; })()"
            % hit_index
        )
        check(results, "时间轴直接跳到 found 步骤",
              await cdp.js(f"window.__classroom.getState().index === {hit_index} && document.querySelectorAll('[data-component-id=\"array\"] .cell.found:not([hidden])').length === 2"),
              f"index={hit_index}")
        check(results, "命中步骤代码和行为命中提示",
              await cdp.js("document.querySelector('.code-line.active .no').textContent === '6' && document.querySelector('#hint-title').textContent.includes('返回答案') && document.querySelectorAll('[data-component-id=\"hash_map\"] tr.hit').length >= 1"),
              await cdp.js("document.querySelector('#hint-title').textContent"))
        await cdp.js("document.querySelector('#hint-toggle').click()")
        check(results, "展开参考答案",
              await cdp.js("!document.querySelector('#hint-answer').hidden && document.querySelector('#hint-answer').textContent.length > 10"),
              await cdp.js("document.querySelector('#hint-answer').textContent.slice(0,30)"))
        screenshots.append(await cdp.screenshot("02_normal_hit_hint.png"))

        # 暂停不能继续自动推进。
        await cdp.js("document.querySelector('#reset').click()")
        await cdp.js("document.querySelector('#play').click()")
        await asyncio.sleep(0.25)
        check(results, "自动播放开始后处于 playing 状态",
              await cdp.js("window.__classroom.getState().playing && window.__classroom.getState().mode === 'auto'"),
              await cdp.js("JSON.stringify(window.__classroom.getState())"))
        await cdp.js("document.querySelector('#pause').click()")
        paused_index = await cdp.js("window.__classroom.getState().index")
        await asyncio.sleep(0.8)
        check(results, "暂停后旧定时器停止推进",
              await cdp.js("window.__classroom.getState().playing === false && window.__classroom.getState().index === %d" % paused_index),
              f"paused_index={paused_index}")

        # 速度切换 + 播放中切换到第二个用例，旧定时器必须失效。
        await cdp.js(
            "(() => { const el=document.querySelector('#speed'); el.value='2'; el.dispatchEvent(new Event('change',{bubbles:true})); })()"
        )
        check(results, "速度切换为 2×",
              await cdp.js("window.__classroom.getState().speed === 2"),
              await cdp.js("document.querySelector('#speed').value"))
        await cdp.js("document.querySelector('#play').click()")
        await asyncio.sleep(0.2)
        await cdp.js(
            "window.__reuseProbe = {root:document.querySelector('[data-component-id=\"array\"]'),"
            "comp:window.__classroom.components.get('array'),size:window.__classroom.components.size};"
            "window.__reuseProbe.comp.__probe = 'kept';"
        )
        await cdp.js("document.querySelector('.case-card[data-case-id=\"first\"]').click()")
        await asyncio.sleep(0.2)
        check(
            results,
            "切换用例复用同一批 DOM 组件与 VisualPlan",
            await cdp.js(
                "window.__reuseProbe.root === document.querySelector('[data-component-id=\"array\"]')"
                " && window.__reuseProbe.comp === window.__classroom.components.get('array')"
                " && window.__reuseProbe.comp.__probe === 'kept'"
                " && window.__classroom.components.size === 4"
                " && window.__reuseProbe.size === 4"
            ),
            await cdp.js("window.__reuseProbe.size"),
        )
        check(results, "播放中切换 Case 2 后从初始状态开始",
              await cdp.js("window.__classroom.getState().caseId === 'first' && window.__classroom.getState().index === 0 && window.__classroom.getState().playing === false"),
              await cdp.js("JSON.stringify(window.__classroom.getState())"))
        check(results, "Case 2 数组、target、空哈希表",
              await cdp.js("JSON.stringify([...document.querySelectorAll('[data-component-id=\"array\"] .cell:not([hidden]) .value')].map(n=>n.textContent)) === JSON.stringify(['3','2','4']) && document.querySelector('[data-component-id=\"array\"] .array-target').textContent.includes('5') && document.querySelectorAll('[data-component-id=\"hash_map\"] tbody tr').length === 0"),
              await cdp.js("document.querySelector('[data-component-id=\"array\"] .array-target').textContent"))
        screenshots.append(await cdp.screenshot("03_case2_initial_after_switch.png"))
        await asyncio.sleep(1.3)
        check(results, "Case 2 切换后不会被 Case 1 旧定时器推进",
              await cdp.js("window.__classroom.getState().caseId === 'first' && window.__classroom.getState().index === 0"),
              await cdp.js("JSON.stringify(window.__classroom.getState())"))

        # Case 2 自动播放 -> 暂停 -> 继续。
        await cdp.js("document.querySelector('#auto').click()")
        await asyncio.sleep(1.35)
        check(results, "Case 2 自动播放推进步骤",
              await cdp.js("window.__classroom.getState().playing && window.__classroom.getState().index >= 2"),
              await cdp.js("JSON.stringify(window.__classroom.getState())"))
        screenshots.append(await cdp.screenshot("04_case2_auto_playing.png"))
        await cdp.js("document.querySelector('#pause').click()")
        paused2 = await cdp.js("window.__classroom.getState().index")
        await asyncio.sleep(0.6)
        check(results, "暂停并接管 Case 2",
              await cdp.js("window.__classroom.getState().playing === false && window.__classroom.getState().index === %d" % paused2),
              f"paused_index={paused2}")
        await cdp.js("document.querySelector('#resume').click()")
        await asyncio.sleep(1.1)
        check(results, "继续后从暂停位置向前推进",
              await cdp.js("window.__classroom.getState().playing && window.__classroom.getState().index > %d" % paused2),
              await cdp.js("JSON.stringify(window.__classroom.getState())"))
        await cdp.js("document.querySelector('#pause').click()")

        # 切回 Case 1，状态必须恢复，且不会残留 Case 2。
        await cdp.js("document.querySelector('.case-card[data-case-id=\"normal\"]').click()")
        check(results, "切回 Case 1 恢复数组、target、空哈希表和初始代码行",
              await cdp.js("window.__classroom.getState().caseId === 'normal' && window.__classroom.getState().index === 0 && JSON.stringify([...document.querySelectorAll('[data-component-id=\"array\"] .cell:not([hidden]) .value')].map(n=>n.textContent)) === JSON.stringify(['2','7','11','15']) && document.querySelector('[data-component-id=\"array\"] .array-target').textContent.includes('9') && document.querySelectorAll('[data-component-id=\"hash_map\"] tbody tr').length === 0 && document.querySelector('.code-line.active .no').textContent === '2'"),
              await cdp.js("JSON.stringify({state:window.__classroom.getState(), target:document.querySelector('[data-component-id=\"array\"] .array-target').textContent})"))
        await asyncio.sleep(0.25)
        screenshots.append(await cdp.screenshot("05_case1_restored.png"))

        # 4.8 秒内自动播完 8 步（2×）。
        await cdp.js("document.querySelector('#auto').click()")
        await asyncio.sleep(5.3)
        check(results, "自动播放到末尾后停止",
              await cdp.js("window.__classroom.getState().playing === false && window.__classroom.getState().atEnd === true && window.__classroom.getState().index === 7"),
              await cdp.js("JSON.stringify(window.__classroom.getState())"))
        screenshots.append(await cdp.screenshot("06_auto_complete.png"))

        # 错误用例没有伪造轨迹，必须显示错误且禁用播放。
        await cdp.js("document.querySelector('.case-card[data-case-id=\"invalid\"]').click()")
        check(results, "无效用例显示错误且不可播放",
              await cdp.js("window.__classroom.getState().count === 0 && !document.querySelector('#case-error').hidden && document.querySelector('#step-title').textContent === '不可播放' && document.querySelector('#play').disabled === true"),
              await cdp.js("document.querySelector('#case-error').textContent"))
        await asyncio.sleep(0.25)
        screenshots.append(await cdp.screenshot("07_invalid_case.png"))

        # 逐个真实切换全部 10 个用例，检查步数、输入数组和 target 没有串台。
        case_ids = await cdp.js("window.__classroom.deck.cases.map(c=>c.case_id)")
        catalog: list[dict[str, Any]] = []
        for case_id in case_ids:
            await cdp.js(
                "document.querySelector('.case-card[data-case-id=%s]').click()" % json.dumps(case_id)
            )
            selected = await cdp.js(
                "JSON.stringify({caseId:window.__classroom.getState().caseId,"
                "count:window.__classroom.getState().count,index:window.__classroom.getState().index,"
                "playing:window.__classroom.getState().playing,"
                "values:[...document.querySelectorAll('[data-component-id=\"array\"] .cell:not([hidden]) .value')].map(n=>n.textContent),"
                "target:document.querySelector('[data-component-id=\"array\"] .array-target').hidden ? null : document.querySelector('[data-component-id=\"array\"] .array-target').textContent,"
                "errorHidden:document.querySelector('#case-error').hidden})"
            )
            item = json.loads(selected)
            expected = await cdp.js(
                "(() => { const c=window.__classroom.deck.cases.find(x=>x.case_id===%s);"
                "return JSON.stringify({count:(c.trace&&c.trace.steps||[]).length,"
                "nums:c.input_data&&c.input_data.nums||[],target:c.input_data&&c.input_data.target}); })()"
                % json.dumps(case_id)
            )
            expected_data = json.loads(expected)
            values_ok = item["values"] == [str(value) for value in expected_data["nums"]] if expected_data["count"] else item["values"] == []
            target_ok = item["target"] is None if expected_data["count"] == 0 else (
                item["target"] is not None and str(expected_data["target"]) in item["target"]
            )
            catalog.append({"case_id": case_id, **item, "expected": expected_data})
            check(
                results,
                f"用例目录切换正确：{case_id}",
                item["caseId"] == case_id
                and item["count"] == expected_data["count"]
                and item["index"] == 0
                and item["playing"] is False
                and values_ok
                and target_ok,
                {"actual": item, "expected": expected_data},
            )
        payload["case_catalog"] = catalog
        await cdp.js("document.querySelector('.case-card[data-case-id=\"normal\"]').click()")

        external = await cdp.js(
            "performance.getEntriesByType('resource').map(e=>e.name).filter(u=>/^https?:/i.test(u))"
        )
        check(results, "完全离线：没有 HTTP(S) 资源请求", external == [], external)
        check(results, "浏览器端没有脚本错误", await cdp.js("window.__classroomErrors.length === 0"),
              await cdp.js("window.__classroomErrors"))

        payload.update(
            {
                "passed": all(item["passed"] for item in results),
                "elapsed_seconds": round(time.time() - started, 2),
                "screenshots": screenshots,
                "final_state": await cdp.js("window.__classroom.getState()"),
                "external_requests": external,
                "browser_errors": await cdp.js("window.__classroomErrors"),
                "network_request_count": len([e for e in cdp.events if e.get("method") == "Network.requestWillBeSent"]),
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
                payload["browser_errors"] = await cdp.js("window.__classroomErrors || []")
            except Exception:  # noqa: BLE001
                pass
        return 1
    finally:
        if cdp is not None:
            try:
                await cdp.close()
            except Exception:  # noqa: BLE001
                pass
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)
        (OUT_DIR / "browser_check.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("\n结果：", OUT_DIR / "browser_check.json")
        print(json.dumps({k: v for k, v in payload.items() if k not in {"checks", "traceback"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
