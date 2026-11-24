"""批量任务文件解析（JSON）。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Settings, get_settings
from .protocol.teaching import BatchFile, RenderOptions, TaskSpec


def default_render_options(settings: Settings | None = None) -> RenderOptions:
    settings = settings or get_settings()
    return RenderOptions(
        theme=settings.theme,
        resolution=settings.resolution,
        fps=settings.fps,
        max_seconds=settings.max_seconds,
        voice=settings.voice,
        tts_provider=settings.tts_provider,
        render_quality=settings.render_quality,
    )


def _build_task(raw: dict[str, Any], defaults: RenderOptions) -> TaskSpec:
    options_raw = dict(defaults.model_dump())
    options_raw.update(raw.get("options") or {})
    options = RenderOptions.model_validate(options_raw)
    payload = {key: value for key, value in raw.items() if key not in {"id", "options"}}
    payload["options"] = options
    payload["task_id"] = raw.get("id")
    return TaskSpec.model_validate(payload)


def load_batch(path: str | Path, settings: Settings | None = None) -> tuple[str, list[TaskSpec]]:
    settings = settings or get_settings()
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        data = {"batch_name": path.stem, "tasks": data}
    if not isinstance(data, dict) or "tasks" not in data:
        raise ValueError("批量文件必须是任务数组，或包含 tasks 字段的对象")
    defaults_raw = dict(default_render_options(settings).model_dump())
    defaults_raw.update(data.get("defaults") or {})
    defaults = RenderOptions.model_validate(defaults_raw)
    tasks: list[TaskSpec] = []
    for index, raw in enumerate(data["tasks"]):
        if isinstance(raw, str):
            tasks.append(TaskSpec(prompt=raw, task_id=f"task_{index + 1}", options=defaults))
            continue
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index + 1} 个任务格式错误，应为字符串或对象")
        if not raw.get("id"):
            raw = {**raw, "id": f"task_{index + 1}"}
        try:
            tasks.append(_build_task(raw, defaults))
        except Exception as exc:  # noqa: BLE001 - 给出可定位的错误
            raise ValueError(f"第 {index + 1} 个任务（{raw.get('id')}）校验失败：{exc}") from exc
    if not tasks:
        raise ValueError("批量文件中没有任务")
    return str(data.get("batch_name") or path.stem), tasks


def load_batch_file_strict(path: str | Path, settings: Settings | None = None) -> BatchFile:
    settings = settings or get_settings()
    name, tasks = load_batch(path, settings)
    return BatchFile(batch_name=name, defaults=default_render_options(settings), tasks=tasks)
