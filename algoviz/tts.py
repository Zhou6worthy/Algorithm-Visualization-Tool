"""语音合成：Edge TTS（默认，中文自然）→ Windows SAPI（离线兜底）→ 静音。"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Settings, get_settings
from .media import MediaError, probe_duration

log = logging.getLogger("algoviz.tts")

EDGE_VOICE = "zh-CN-XiaoxiaoNeural"

_SPEECH_REPLACEMENTS = [
    (r"\[([^\[\]]*)\]", r" \1 "),
    (r"→", "到"),
    (r"≤", "小于等于"),
    (r"≥", "大于等于"),
    (r"∞", "无穷大"),
    (r"≈", "约等于"),
    (r"×", "乘"),
    (r"⇒", "推出"),
    (r"±", "正负"),
    (r"[“”]", ""),
    (r"[*#`_]", ""),
]


def speech_text(text: str) -> str:
    value = text
    for pattern, repl in _SPEECH_REPLACEMENTS:
        value = re.sub(pattern, repl, value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or text


def estimate_duration(text: str) -> float:
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_words = len(re.findall(r"[A-Za-z0-9_]+", text))
    return round(cjk / 4.6 + latin_words * 0.22 + 0.6, 3)


@dataclass
class AudioResult:
    text: str
    path: Path | None
    duration: float
    provider: str
    error: str | None = None


class TTSEngine:
    def __init__(
        self,
        settings: Settings | None = None,
        provider: str | None = None,
        voice: str | None = None,
        rate: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = (provider or self.settings.tts_provider or "auto").lower()
        self.voice = voice or self.settings.voice or EDGE_VOICE
        self.rate = rate or self.settings.tts_rate or "+0%"

    def synthesize(self, texts: list[str], out_dir: Path, prefix: str = "seg") -> list[AudioResult]:
        out_dir.mkdir(parents=True, exist_ok=True)
        if self.provider in {"none", "silent"}:
            return [
                AudioResult(text=text, path=None, duration=estimate_duration(text), provider="silent")
                for text in texts
            ]
        results: list[AudioResult] = []
        if self.provider in {"auto", "edge"}:
            results = self._synthesize_edge(texts, out_dir, prefix)
        if self.provider == "sapi" or self.provider not in {"auto", "edge", "sapi"}:
            results = [
                AudioResult(text=text, path=None, duration=estimate_duration(text), provider="pending", error="未启用")
                for text in texts
            ]
        for index, result in enumerate(results):
            if result.path is not None and result.path.exists():
                continue
            fallback = self._synthesize_sapi(result.text, out_dir / f"{prefix}_{index:02d}.wav")
            if fallback is not None:
                results[index] = AudioResult(
                    text=result.text,
                    path=fallback,
                    duration=probe_duration(fallback, self.settings),
                    provider="sapi",
                    error=result.error,
                )
            else:
                results[index] = AudioResult(
                    text=result.text,
                    path=None,
                    duration=estimate_duration(result.text),
                    provider="silent",
                    error=result.error or "TTS 不可用，使用静音与估算时长",
                )
        return results

    # ------------------------------------------------------------------ Edge TTS
    def _synthesize_edge(self, texts: list[str], out_dir: Path, prefix: str) -> list[AudioResult]:
        results: list[AudioResult] = [
            AudioResult(text=text, path=None, duration=estimate_duration(text), provider="pending")
            for text in texts
        ]

        async def worker(index: int, sem: asyncio.Semaphore) -> None:
            import edge_tts

            text = speech_text(texts[index])
            path = out_dir / f"{prefix}_{index:02d}.mp3"
            last_error: str | None = None
            async with sem:
                for attempt in range(2):
                    try:
                        communicator = edge_tts.Communicate(text, self.voice, rate=self.rate)
                        await communicator.save(str(path))
                        if path.exists() and path.stat().st_size > 2000:
                            duration = probe_duration(path, self.settings)
                            results[index] = AudioResult(text=texts[index], path=path, duration=duration, provider="edge")
                            return
                        last_error = "Edge TTS 输出文件为空"
                    except Exception as exc:  # noqa: BLE001 - 网络服务
                        last_error = f"{type(exc).__name__}: {exc}"
                        await asyncio.sleep(0.8 + attempt)
            results[index] = AudioResult(
                text=texts[index], path=None, duration=estimate_duration(texts[index]), provider="edge", error=last_error
            )

        async def run_all() -> None:
            sem = asyncio.Semaphore(4)
            await asyncio.gather(*(worker(i, sem) for i in range(len(texts))))

        try:
            asyncio.run(run_all())
        except Exception as exc:  # noqa: BLE001
            log.warning("Edge TTS 批量合成失败：%s", exc)
        return results

    # ------------------------------------------------------------------ Windows SAPI
    def _synthesize_sapi(self, text: str, out_path: Path) -> Path | None:
        if shutil.which("powershell.exe") is None and shutil.which("pwsh") is None:
            return None
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
        txt_path = out_path.with_suffix(".txt")
        txt_path.write_text(speech_text(text), encoding="utf-8")
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$zh = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'zh*' } | Select-Object -First 1; "
            "if ($zh) { $s.SelectVoice($zh.VoiceInfo.Name) }; "
            f"$text = [System.IO.File]::ReadAllText('{str(txt_path).replace(chr(39), chr(39) * 2)}', [System.Text.Encoding]::UTF8); "
            f"$s.SetOutputToWaveFile('{str(out_path).replace(chr(39), chr(39) * 2)}'); "
            "$s.Speak($text); "
            "$s.Dispose()"
        )
        try:
            proc = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                timeout=180,
            )
            if proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 1000:
                return out_path
            log.warning("SAPI 合成失败：%s", proc.stderr.decode("utf-8", "replace")[-300:])
        except Exception as exc:  # noqa: BLE001
            log.warning("SAPI 合成异常：%s", exc)
        return None


def audio_duration(path: Path, settings: Settings | None = None) -> float:
    try:
        return probe_duration(path, settings)
    except MediaError:
        return estimate_duration("")
