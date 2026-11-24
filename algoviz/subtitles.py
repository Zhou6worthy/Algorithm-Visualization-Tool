"""字幕导出（SRT）。"""
from __future__ import annotations

from pathlib import Path

from .protocol.teaching import SubtitleCue
from .timeline import wrap_subtitle


def _timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        millis = 999
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(cues: list[SubtitleCue], path: str | Path, *, wrap: bool = True) -> Path:
    path = Path(path)
    lines: list[str] = []
    for index, cue in enumerate(cues, start=1):
        text = wrap_subtitle(cue.text, width=34, max_lines=2) if wrap else cue.text
        lines.append(str(index))
        lines.append(f"{_timestamp(cue.start)} --> {_timestamp(cue.end)}")
        lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8-sig")
    return path
