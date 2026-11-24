"""FFmpeg / FFprobe 封装。"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from .config import Settings, get_settings

log = logging.getLogger("algoviz.media")


class MediaError(RuntimeError):
    pass


def run_cmd(
    args: list[str],
    *,
    timeout: float = 900.0,
    check: bool = True,
    cwd: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    log.debug("run: %s", " ".join(args))
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
        )
    except FileNotFoundError as exc:
        raise MediaError(f"找不到可执行文件：{args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"命令执行超时（{timeout:.0f}s）：{' '.join(args[:3])}") from exc
    if check and proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-6:]
        raise MediaError(f"命令执行失败（exit {proc.returncode}）：" + " | ".join(tail))
    return proc


def ffprobe_info(path: str | Path, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    proc = run_cmd(
        [
            settings.ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        timeout=60,
    )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise MediaError(f"ffprobe 输出无法解析：{path}") from exc


def probe_duration(path: str | Path, settings: Settings | None = None) -> float:
    info = ffprobe_info(path, settings)
    try:
        return float(info["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        for stream in info.get("streams", []):
            if stream.get("duration"):
                return float(stream["duration"])
    raise MediaError(f"无法读取媒体时长：{path}")


def probe_streams(path: str | Path, settings: Settings | None = None) -> dict[str, Any]:
    info = ffprobe_info(path, settings)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    return {
        "duration": float(info.get("format", {}).get("duration", 0.0)),
        "size": int(info.get("format", {}).get("size", 0) or 0),
        "video": video,
        "audio": audio,
        "format_name": info.get("format", {}).get("format_name"),
    }


def make_silence(path: str | Path, duration: float, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    run_cmd(
        [
            settings.ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-t",
            f"{max(0.05, duration):.3f}",
            "-c:a",
            "pcm_s16le",
            str(path),
        ]
    )


def pad_audio(src: str | Path, dst: str | Path, duration: float, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    run_cmd(
        [
            settings.ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(src),
            "-af",
            f"apad=whole_dur={max(0.05, duration):.3f}",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            "-t",
            f"{max(0.05, duration):.3f}",
            str(dst),
        ]
    )


def concat_audio(files: list[Path], dst: str | Path, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if not files:
        raise MediaError("没有可拼接的音频文件")
    list_file = Path(dst).with_suffix(".concat.txt")
    lines = []
    for file in files:
        escaped = file.as_posix().replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_file.write_text("\n".join(lines), encoding="utf-8")
    run_cmd(
        [
            settings.ffmpeg,
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:a",
            "pcm_s16le",
            str(dst),
        ]
    )


def mux_video_audio(
    video: str | Path,
    audio: str | Path | None,
    out: str | Path,
    duration: float | None = None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    args = [settings.ffmpeg, "-y", "-v", "error", "-i", str(video)]
    if audio is not None:
        args += ["-i", str(audio)]
    args += ["-map", "0:v:0"]
    if audio is not None:
        args += ["-map", "1:a:0", "-c:a", "aac", "-b:a", "192k"]
    args += ["-c:v", "copy", "-movflags", "+faststart"]
    if duration is not None:
        args += ["-t", f"{duration:.3f}"]
    args.append(str(out))
    run_cmd(args)


def trim_video(src: str | Path, dst: str | Path, duration: float, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    run_cmd(
        [
            settings.ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(src),
            "-t",
            f"{duration:.3f}",
            "-c",
            "copy",
            str(dst),
        ]
    )
