"""AI 配置的读写：只把 Key 写入本机 .env，接口永不回显完整 Key。"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ..config import Settings
from .client import AIClient

_ENV_KEYS = (
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "ALGOVIZ_AI_MODE",
)


def mask_key(key: str) -> str:
    key = key.strip()
    if not key:
        return ""
    if len(key) <= 10:
        return key[:2] + "***" + key[-2:]
    return key[:6] + "..." + key[-4:]


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def upsert_env(path: Path, updates: dict[str, str]) -> None:
    """只更新指定键，保留其他配置与注释。"""
    for key, value in updates.items():
        if "\n" in value or "\r" in value:
            raise ValueError(f"{key} 不能包含换行")
    lines = _read_lines(path)
    remaining = dict(updates)
    output: list[str] = []
    for line in lines:
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match and match.group(1) in remaining:
            key = match.group(1)
            output.append(f"{key}={remaining.pop(key)}")
        else:
            output.append(line)
    for key, value in remaining.items():
        output.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    os.replace(temp, path)


def ai_public_settings(settings: Settings, ai: AIClient, *, last_test: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "provider": "deepseek",
        "has_key": bool(settings.deepseek_api_key),
        "masked_key": mask_key(settings.deepseek_api_key),
        "model": settings.deepseek_model,
        "base_url": settings.deepseek_base_url,
        "mode": settings.ai_mode,
        "enabled": ai.available,
        "env_file": str(settings.env_path),
        "last_error": ai.last_error,
        "last_test": last_test,
    }


def update_ai_settings(
    settings: Settings,
    ai: AIClient,
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    mode: str | None = None,
    clear_key: bool = False,
) -> dict[str, Any]:
    updates: dict[str, str] = {}
    if clear_key:
        updates["DEEPSEEK_API_KEY"] = ""
        settings.deepseek_api_key = ""
    elif api_key is not None and api_key.strip():
        key = api_key.strip()
        if any(ch.isspace() for ch in key):
            raise ValueError("API Key 不能包含空白字符")
        updates["DEEPSEEK_API_KEY"] = key
        settings.deepseek_api_key = key
    if model is not None:
        model = model.strip()
        if not model:
            raise ValueError("模型名不能为空")
        if not re.fullmatch(r"[A-Za-z0-9_.\-]{2,64}", model):
            raise ValueError("模型名格式不合法")
        updates["DEEPSEEK_MODEL"] = model
        settings.deepseek_model = model
    if base_url is not None:
        base_url = base_url.strip().rstrip("/")
        if not re.match(r"^https?://", base_url):
            raise ValueError("Base URL 必须以 http:// 或 https:// 开头")
        updates["DEEPSEEK_BASE_URL"] = base_url
        settings.deepseek_base_url = base_url
    if mode is not None:
        mode = mode.strip().lower()
        if mode not in {"auto", "on", "off"}:
            raise ValueError("AI 模式只能是 auto / on / off")
        updates["ALGOVIZ_AI_MODE"] = mode
        settings.ai_mode = mode
    if updates:
        upsert_env(settings.env_path, updates)
    ai.settings = settings
    ai.reset_connection()
    return ai_public_settings(settings, ai)
