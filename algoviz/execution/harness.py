"""在受控子进程中执行 user_solution.py 的 harness。

user_solution.py 保持用户原始源码；本文件是独立 harness，不参与追踪。
输出通道：
- frames.jsonl：GenericTracer 事件；
- result.json：返回值/异常/stdout/hash/trace 完整性；
- stdout/stderr：用户 stdout 被 BoundedTextIO 捕获。
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

# 不生成用户源码旁边的 __pycache__，保持 user_solution.py 目录原样。
sys.dont_write_bytecode = True

from ..protocol.execution import (
    ExecutionStatus,
    TraceLimits,
)
from .collector import BoundedTextIO, PythonTraceCollector
from .safe_serializer import SafeSerializer


def _sha256_file(path: str) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_user_module(user_path: str) -> Any:
    spec = importlib.util.spec_from_file_location("algo_user_solution", user_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载用户代码：{user_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["algo_user_solution"] = module
    spec.loader.exec_module(module)
    return module


def _resolve_callable(module: Any, style: str, entry_point: str) -> Any:
    if style == "function":
        target = getattr(module, entry_point, None)
        if not callable(target):
            raise AttributeError(f"入口函数不存在：{entry_point}")
        return target
    if style == "leetcode_class":
        if "." not in entry_point:
            raise ValueError("LeetCode 类入口必须形如 Solution.two_sum")
        class_name, method_name = entry_point.split(".", 1)
        cls = getattr(module, class_name, None)
        if cls is None:
            raise AttributeError(f"类不存在：{class_name}")
        instance = cls()
        target = getattr(instance, method_name, None)
        if not callable(target):
            raise AttributeError(f"方法不存在：{entry_point}")
        return target
    raise ValueError(f"M1 暂不支持执行风格：{style}")


def _write_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if len(argv) != 4:
        raise SystemExit("usage: harness.py USER INPUT_JSON FRAMES_JSON RESULT_JSON")
    user_path = os.path.realpath(argv[0])
    input_path, frames_path, result_path = argv[1], argv[2], argv[3]
    source_hash = _sha256_file(user_path)
    limits = TraceLimits()
    with open(input_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    style = payload.get("style", "function")
    entry_point = payload.get("entry_point", "two_sum")
    args = payload.get("args", [])
    kwargs = payload.get("kwargs", {}) or {}
    serializer = SafeSerializer()
    stdout_writer = BoundedTextIO(limits.max_stdout_bytes)
    stderr_writer = BoundedTextIO(limits.max_stdout_bytes)
    collector = PythonTraceCollector(user_path, limits=limits, serializer=serializer, stdout=stdout_writer)
    started = time.time()
    result_status = ExecutionStatus.OK
    exception_type = None
    exception_message = None
    return_value = None
    try:
        module = _load_user_module(user_path)
        target = _resolve_callable(module, style, entry_point)
        # 只在真正调用用户入口时安装追踪；模块导入本身不进入 trace。
        sys.settrace(collector.trace)
        try:
            with redirect_stdout(stdout_writer), redirect_stderr(stderr_writer):
                return_value = target(*args, **kwargs)
        finally:
            sys.settrace(None)
    except BaseException as exc:  # noqa: BLE001 - 捕获用户异常，写入结果
        exception_type = type(exc).__name__
        exception_message = str(exc)
        result_status = ExecutionStatus.SANDBOX_ERROR
        # 如果异常发生在入口调用前，trace 可能尚未安装
    trace = collector.finish()
    trace.source_hash = source_hash
    if result_status == ExecutionStatus.OK and not trace.trace_complete:
        result_status = (
            ExecutionStatus.EVENT_LIMIT if collector.limit_hit else ExecutionStatus.TRACE_INCOMPLETE
        )
    if stdout_writer.truncated or stderr_writer.truncated:
        result_status = ExecutionStatus.OUTPUT_LIMIT
    serialized_return = serializer.serialize(return_value)
    result = {
        "status": result_status.value,
        "source_hash": source_hash,
        "trace_complete": trace.trace_complete,
        "event_count": trace.event_count,
        "return_value": serializer.to_native(serialized_return),
        "exception_type": exception_type,
        "exception_message": exception_message,
        "stdout": stdout_writer.getvalue(),
        "stderr": stderr_writer.getvalue(),
        "stdout_truncated": stdout_writer.truncated,
        "duration_ms": round((time.time() - started) * 1000, 3),
        "entry_point": entry_point,
        "style": style,
    }
    if trace.events:
        result["terminal_event_id"] = trace.events[-1].event_id
        result["terminal_event"] = trace.events[-1].event
    # frames.jsonl 由 harness 独占写入；用户代码没有拿到该路径的意图。
    try:
        with open(frames_path, "w", encoding="utf-8") as handle:
            handle.write(trace.model_dump_json())
            handle.flush()
    except Exception as exc:  # noqa: BLE001
        result["status"] = ExecutionStatus.TRACE_INCOMPLETE.value
        result["trace_complete"] = False
        result["frames_write_error"] = str(exc)
    _write_json(result_path, result)
    return 0 if result["trace_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
