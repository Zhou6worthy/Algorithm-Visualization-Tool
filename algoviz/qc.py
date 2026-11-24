"""视频质量检查：分辨率、时长、音轨、关键帧是否空白。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from .config import Settings, get_settings
from .media import MediaError, probe_streams, run_cmd

log = logging.getLogger("algoviz.qc")


@dataclass
class QCReport:
    ok: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str, *, hard: bool = True) -> None:
        self.checks.append({"name": name, "ok": ok, "detail": detail, "hard": hard})
        if not ok:
            if hard:
                self.errors.append(f"{name}: {detail}")
                self.ok = False
            else:
                self.warnings.append(f"{name}: {detail}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def _sample_brightness(video: Path, timestamp: float, frame_path: Path, settings: Settings) -> tuple[float, float]:
    run_cmd(
        [
            settings.ffmpeg,
            "-y",
            "-v",
            "error",
            "-ss",
            f"{max(0.0, timestamp):.2f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(frame_path),
        ]
    )
    if not frame_path.exists():
        return 0.0, 0.0
    with Image.open(frame_path) as image:
        gray = image.convert("L")
        stat = ImageStat.Stat(gray)
        return float(stat.mean[0]), float(stat.stddev[0])


def inspect_video(
    video: Path,
    *,
    expected_duration: float,
    expected_resolution: tuple[int, int],
    expected_fps: int,
    expect_audio: bool,
    verified: bool,
    settings: Settings | None = None,
    work_dir: Path | None = None,
) -> QCReport:
    settings = settings or get_settings()
    report = QCReport(ok=True)
    if not video.exists():
        report.add("文件存在", False, str(video))
        return report
    size = video.stat().st_size
    report.add("文件大小", size > 20_000, f"{size / 1024:.0f} KB")
    try:
        info = probe_streams(video, settings)
    except MediaError as exc:
        report.add("媒体探测", False, str(exc))
        return report
    duration = float(info.get("duration") or 0.0)
    report.add("视频时长", duration > 5.0, f"{duration:.2f}s")
    drift = abs(duration - expected_duration)
    report.add(
        "时长与计划一致",
        drift <= 1.5,
        f"计划 {expected_duration:.2f}s，实际 {duration:.2f}s（差 {drift:.2f}s）",
    )
    video_stream = info.get("video")
    if not video_stream:
        report.add("视频流", False, "未找到视频流")
        return report
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    report.add(
        "分辨率",
        (width, height) == tuple(expected_resolution),
        f"{width}x{height}，期望 {expected_resolution[0]}x{expected_resolution[1]}",
        hard=False,
    )
    fps_raw = str(video_stream.get("avg_frame_rate") or "0/1")
    try:
        num, den = fps_raw.split("/")
        fps = float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    report.add("帧率", abs(fps - expected_fps) < 0.5, f"{fps:.2f} FPS", hard=False)
    codec = video_stream.get("codec_name")
    report.add("编码", codec in {"h264", "hevc"}, f"{codec}", hard=False)
    audio_stream = info.get("audio")
    if expect_audio:
        report.add("音轨", audio_stream is not None, "有音轨" if audio_stream else "缺少音轨", hard=False)
    report.add("算法校验", verified, "追踪结果通过独立参考实现校验" if verified else "算法结果未通过校验")
    # 关键帧空白检查
    if work_dir is not None and duration > 4:
        frames_dir = work_dir / "qc_frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        samples = [max(1.0, duration * 0.25), duration * 0.5, max(1.0, duration - 2.0)]
        non_blank = 0
        details = []
        for index, timestamp in enumerate(samples):
            frame_path = frames_dir / f"frame_{index}.png"
            try:
                mean, std = _sample_brightness(video, timestamp, frame_path, settings)
            except MediaError as exc:
                report.add("抽帧检查", False, str(exc), hard=False)
                break
            details.append(f"{timestamp:.1f}s: mean={mean:.1f}, std={std:.1f}")
            if mean > 6 and std > 4:
                non_blank += 1
        if details:
            report.add("关键帧非空白", non_blank >= 2, "；".join(details), hard=False)
    return report
