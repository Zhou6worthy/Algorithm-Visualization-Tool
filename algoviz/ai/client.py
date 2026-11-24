"""DeepSeek 客户端：OpenAI 兼容协议，JSON 输出，失败自动降级。

额外提供线程内的调用统计（start_usage / finish_usage），
让每个任务都能明确报告“是否真的调用了大模型”。
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any

from ..config import Settings, get_settings

log = logging.getLogger("algoviz.ai")


def _strip_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        text = text[start : end + 1]
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


class _TruncatedJSON(ValueError):
    pass


class AIClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.last_error: str | None = None
        self._client: Any = None
        self._disabled = False
        self._local = threading.local()

    @property
    def available(self) -> bool:
        return self.settings.ai_available and not self._disabled

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
                timeout=90.0,
                max_retries=1,
            )
        return self._client

    def reset_connection(self) -> None:
        """Key / BaseURL / 模型变更后重建客户端。"""
        self._client = None
        self._disabled = False
        self.last_error = None

    # ------------------------------------------------------------------ 用量统计
    def start_usage(self) -> None:
        self._local.active = True
        self._local.started = time.time()
        self._local.calls = []

    def _record(
        self,
        purpose: str,
        ok: bool,
        *,
        error: str | None = None,
        latency_ms: float = 0.0,
    ) -> None:
        if not getattr(self._local, "active", False):
            return
        self._local.calls.append(
            {
                "purpose": purpose,
                "ok": ok,
                "error": error,
                "latency_ms": round(latency_ms, 1),
                "model": self.settings.deepseek_model,
            }
        )

    def finish_usage(self) -> dict[str, Any]:
        calls = list(getattr(self._local, "calls", []))
        self._local.active = False
        successes = sum(1 for item in calls if item["ok"])
        failures = len(calls) - successes
        errors = [item["error"] for item in calls if item["error"]]
        if not self.available and not calls:
            status = "disabled"
            reason = (
                "未配置 DEEPSEEK_API_KEY"
                if not self.settings.deepseek_api_key
                else "ALGOVIZ_AI_MODE=off"
            )
        elif successes:
            status = "used"
            reason = ""
        elif failures:
            status = "failed"
            reason = errors[-1] if errors else "大模型调用失败"
        else:
            status = "unused"
            reason = "任务未触发大模型调用"
        return {
            "provider": "deepseek",
            "status": status,
            "reason": reason,
            "enabled": self.available,
            "has_key": bool(self.settings.deepseek_api_key),
            "mode": self.settings.ai_mode,
            "model": self.settings.deepseek_model,
            "base_url": self.settings.deepseek_base_url,
            "calls": len(calls),
            "successes": successes,
            "failures": failures,
            "last_error": errors[-1] if errors else None,
            "details": calls,
        }

    # ------------------------------------------------------------------ 调用
    def chat_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2600,
        purpose: str = "general",
    ) -> dict[str, Any] | None:
        if not self.available:
            return None
        attempts = 2
        tokens = max_tokens
        for attempt in range(attempts):
            started = time.time()
            try:
                client = self._get_client()
                response = client.chat.completions.create(
                    model=self.settings.deepseek_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                    max_tokens=tokens,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content or ""
                stripped = _strip_json(content)
                try:
                    data = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    finish = getattr(response.choices[0], "finish_reason", None)
                    raise _TruncatedJSON(
                        f"模型返回的 JSON 不完整（finish_reason={finish}，"
                        f"max_tokens={tokens}；推理模型可能耗尽 token）：{content[:80]!r}"
                    ) from exc
                if not isinstance(data, dict):
                    raise ValueError("模型返回的不是 JSON 对象")
                self.last_error = None
                self._record(purpose, True, latency_ms=(time.time() - started) * 1000)
                return data
            except _TruncatedJSON as exc:
                message = str(exc)
                self.last_error = message
                self._record(
                    purpose,
                    False,
                    error=message,
                    latency_ms=(time.time() - started) * 1000,
                )
                log.warning("DeepSeek 返回被截断（第 %s 次，%s）：%s", attempt + 1, purpose, message)
                if attempt + 1 < attempts and tokens < 8000:
                    tokens = min(8000, tokens * 2)
                    continue
                return None
            except Exception as exc:  # noqa: BLE001 - 外部服务，需要降级
                message = f"{type(exc).__name__}: {exc}"
                self.last_error = message
                self._record(
                    purpose,
                    False,
                    error=message,
                    latency_ms=(time.time() - started) * 1000,
                )
                log.warning("DeepSeek 调用失败（第 %s 次，%s）：%s", attempt + 1, purpose, message)
                lowered = message.lower()
                if "api_key" in lowered or "authentication" in lowered or "401" in message:
                    self._disabled = True
                    break
                time.sleep(1.0 + attempt)
        return None

    def test_connection(self, purpose: str = "test") -> dict[str, Any]:
        """做一次最小 JSON 调用，返回可直接展示给用户的诊断结果。"""
        if not self.settings.deepseek_api_key:
            return {
                "ok": False,
                "error": "未配置 DEEPSEEK_API_KEY",
                "hint": "在设置中填入 Key，或写入项目 .env 后重启服务",
                "latency_ms": None,
                "model": self.settings.deepseek_model,
                "usage": None,
            }
        self.start_usage()
        started = time.time()
        data = self.chat_json(
            '你是连通性测试助手，只输出 JSON。',
            '请只返回 {"ok": true}。',
            temperature=0.0,
            max_tokens=1000,
            purpose=purpose,
        )
        usage = self.finish_usage()
        latency = round((time.time() - started) * 1000, 1)
        return {
            "ok": data is not None and data.get("ok") is True,
            "error": None if data is not None else (self.last_error or usage.get("last_error") or "调用失败"),
            "latency_ms": latency,
            "model": self.settings.deepseek_model,
            "base_url": self.settings.deepseek_base_url,
            "response": data,
            "usage": usage,
        }

    def describe(self) -> dict[str, Any]:
        return {
            "enabled": self.available,
            "mode": self.settings.ai_mode,
            "base_url": self.settings.deepseek_base_url,
            "model": self.settings.deepseek_model,
            "has_key": bool(self.settings.deepseek_api_key),
            "last_error": self.last_error,
        }
