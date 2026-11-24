"""Two Sum M2 端到端教学视频流水线。

流程：读取 M1 产物 -> 五段式计划 -> 中文 TTS -> Manim overview/step_by_step
-> FFmpeg 音轨合成 -> SRT/HTML/manifest。整个流程不重新执行用户代码。
"""
from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..config import Settings, get_settings
from ..media import (
    MediaError,
    concat_audio,
    make_silence,
    mux_video_audio,
    pad_audio,
    probe_duration,
    probe_streams,
)
from ..protocol.m2 import TeachingPlan, VideoTimeline
from ..qc import QCReport, inspect_video
from ..subtitles import write_srt
from ..tts import TTSEngine, estimate_duration
from ..render.m2_renderer import M2Renderer, M2RenderResult
from .html_player import write_html_player
from .two_sum_planner import (
    TeachingPlanError,
    attach_audio,
    build_plan,
    build_timelines,
    load_m1_pair,
    render_plan,
    verify_plan,
)

log = logging.getLogger("algoviz.teaching.m2")

Progress = Callable[[str, str, float], None]


class TeachingPipelineError(RuntimeError):
    pass


@dataclass
class TeachingPipelineResult:
    job_dir: Path
    plan: TeachingPlan
    videos: dict[str, Path] = field(default_factory=dict)
    subtitles: dict[str, Path] = field(default_factory=dict)
    html: Path | None = None
    manifest: Path | None = None
    warnings: list[str] = field(default_factory=list)
    qc: dict[str, Any] = field(default_factory=dict)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


class TwoSumTeachingPipeline:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        renderer: M2Renderer | None = None,
        tts: bool = True,
        voice: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.renderer = renderer or M2Renderer(self.settings)
        self.tts_enabled = tts
        self.voice = voice
        self.warnings: list[str] = []

    def _progress(self, callback: Progress | None, stage: str, message: str, value: float) -> None:
        log.info("[%s %.0f%%] %s", stage, value * 100, message)
        if callback:
            callback(stage, message, value)

    # ------------------------------------------------------------------ 输入
    def _prepare_job(
        self,
        job_dir: Path,
        execution_src: Path,
        animation_src: Path,
    ) -> tuple[Path, Path]:
        job_dir.mkdir(parents=True, exist_ok=True)
        execution = job_dir / "execution.json"
        animation = job_dir / "animation_events.json"
        if execution_src.resolve() != execution.resolve():
            shutil.copy2(execution_src, execution)
        if animation_src.resolve() != animation.resolve():
            shutil.copy2(animation_src, animation)
        return execution, animation

    # ------------------------------------------------------------------ TTS
    def _synthesize(
        self,
        plan: TeachingPlan,
        job_dir: Path,
        progress: Progress | None,
    ) -> TeachingPlan:
        audio_dir = job_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        units = [unit for section in plan.sections for unit in section.narration_units]
        if not self.tts_enabled:
            mapping = {unit.unit_id: (estimate_duration(unit.text), None) for unit in units}
            self.warnings.append("M2 TTS 已关闭；视频为静音，字幕仍保留")
            return attach_audio(plan, mapping)
        self._progress(progress, "tts", f"合成中文配音（{len(units)} 段）", 0.25)
        engine = TTSEngine(self.settings, provider=self.settings.tts_provider, voice=self.voice)
        results = engine.synthesize([unit.text for unit in units], audio_dir, prefix="m2")
        mapping: dict[str, tuple[float, str | None]] = {}
        for unit, result in zip(units, results):
            path = str(result.path) if result.path else None
            mapping[unit.unit_id] = (result.duration, path)
            if result.error:
                self.warnings.append(f"配音 {unit.unit_id}：{result.error}")
        got = sum(1 for duration, path in mapping.values() if path)
        if got == 0:
            self.warnings.append("所有 TTS 均失败，已降级为静音时间轴")
        return attach_audio(plan, mapping)

    # ------------------------------------------------------------------ 音轨
    def _build_narration_track(
        self,
        video: VideoTimeline,
        job_dir: Path,
        progress: Progress | None,
        value: float,
    ) -> tuple[Path | None, bool]:
        job_dir = Path(job_dir).resolve()
        audio_dir = job_dir / "audio" / video.variant
        audio_dir.mkdir(parents=True, exist_ok=True)
        cues = [cue for section in video.sections for cue in section.narration_units]
        cues.sort(key=lambda item: item.start)
        has_voice = any(cue.audio_path and Path(cue.audio_path).exists() for cue in cues)
        if not has_voice:
            target = job_dir / f"{video.variant}_narration.wav"
            make_silence(target, video.total_duration, self.settings)
            return target, False
        self._progress(progress, "audio", f"拼接 {video.variant} 配音音轨", value)
        parts: list[Path] = []
        cursor = 0.0
        for index, cue in enumerate(cues):
            gap = max(0.0, cue.start - cursor)
            if gap > 0.015:
                gap_path = audio_dir / f"gap_{index:02d}.wav"
                make_silence(gap_path, gap, self.settings)
                parts.append(gap_path)
            length = max(0.2, cue.duration)
            if cue.audio_path and Path(cue.audio_path).exists():
                padded = audio_dir / f"cue_{index:02d}.wav"
                pad_audio(cue.audio_path, padded, length, self.settings)
                parts.append(padded)
            else:
                silent = audio_dir / f"cue_{index:02d}.wav"
                make_silence(silent, length, self.settings)
                parts.append(silent)
            cursor = max(cursor, cue.start + length)
        tail = max(0.0, video.total_duration - cursor)
        if tail > 0.015:
            tail_path = audio_dir / "tail.wav"
            make_silence(tail_path, tail, self.settings)
            parts.append(tail_path)
        if not parts:
            target = job_dir / f"{video.variant}_narration.wav"
            make_silence(target, video.total_duration, self.settings)
            return target, False
        raw = job_dir / f"{video.variant}_narration_raw.wav"
        target = job_dir / f"{video.variant}_narration.wav"
        concat_audio(parts, raw, self.settings)
        pad_audio(raw, target, video.total_duration, self.settings)
        return target, has_voice

    # ------------------------------------------------------------------ 主流程
    def run(
        self,
        *,
        execution_src: str | Path,
        animation_src: str | Path,
        job_dir: str | Path,
        progress: Progress | None = None,
    ) -> TeachingPipelineResult:
        started = time.time()
        # FFmpeg concat 按清单文件所在目录解析相对路径；统一使用绝对目录避免嵌套。
        job_dir = Path(job_dir).resolve()
        execution_path, animation_path = self._prepare_job(
            job_dir, Path(execution_src), Path(animation_src)
        )
        self._progress(progress, "loading", "读取 M1 真实执行与动画事件", 0.05)
        execution, trace = load_m1_pair(execution_path, animation_path)
        self._progress(progress, "planning", "生成五段式教学计划", 0.12)
        plan = build_plan(
            execution,
            trace,
            execution_file=execution_path,
            animation_file=animation_path,
        )
        plan = self._synthesize(plan, job_dir, progress)
        plan = build_timelines(plan, trace)
        errors = verify_plan(plan, trace)
        if errors:
            raise TeachingPipelineError("教学计划校验失败：" + "；".join(errors))
        plan_path = job_dir / "teaching_plan.json"
        plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        self._progress(
            progress,
            "planning",
            f"计划完成：overview {plan.videos[0].total_duration:.1f}s，"
            f"step_by_step {plan.videos[1].total_duration:.1f}s",
            0.18,
        )

        # HTML 先写，确保即使视频渲染耗时也有可交付产物。
        html = write_html_player(trace, plan, job_dir / "interactive.html")
        result = TeachingPipelineResult(job_dir=job_dir, plan=plan, html=html)
        qc_all: dict[str, Any] = {}
        render_results: dict[str, M2RenderResult] = {}
        videos: dict[str, Path] = {}
        subtitles: dict[str, Path] = {}
        for index, video in enumerate(plan.videos):
            variant = video.variant
            value = 0.25 + index * 0.28
            self._progress(progress, "render", f"Manim 渲染 {variant}（1920×1080）", value)
            rp = render_plan(plan, trace, variant)
            rr = self.renderer.render(rp, job_dir / "render" / variant)
            render_results[variant] = rr
            self._progress(progress, "audio", f"生成 {variant} 中文音轨", value + 0.08)
            narration, has_voice = self._build_narration_track(video, job_dir, progress, value + 0.08)
            final = job_dir / video.output_name
            if narration is not None and narration.exists():
                mux_video_audio(rr.video, narration, final, video.total_duration, self.settings)
            else:
                shutil.copy2(rr.video, final)
            videos[variant] = final
            srt = job_dir / f"{variant}.srt"
            write_srt(video.subtitles, srt)
            subtitles[variant] = srt
            self._progress(progress, "qc", f"检查 {variant} 分辨率、时长与音轨", value + 0.13)
            qc = inspect_video(
                final,
                expected_duration=video.total_duration,
                expected_resolution=(video.width, video.height),
                expected_fps=video.fps,
                expect_audio=has_voice,
                verified=trace.verified,
                settings=self.settings,
                work_dir=job_dir / "qc" / variant,
            )
            stream = probe_streams(final, self.settings)
            width = int((stream.get("video") or {}).get("width") or 0)
            height = int((stream.get("video") or {}).get("height") or 0)
            await_fps = (stream.get("video") or {}).get("avg_frame_rate", "")
            if (width, height) != (video.width, video.height):
                qc.add("固定 1920×1080", False, f"实际 {width}x{height}")
            else:
                qc.add("固定 1920×1080", True, f"{width}x{height}")
            if has_voice and stream.get("audio") is None:
                qc.add("中文配音音轨", False, "缺少音轨")
            elif has_voice:
                qc.add("中文配音音轨", True, "存在 AAC 音轨")
            qc_all[variant] = {
                "ok": qc.ok,
                "checks": qc.checks,
                "warnings": qc.warnings,
                "errors": qc.errors,
                "streams": {
                    "duration": stream.get("duration"),
                    "width": width,
                    "height": height,
                    "fps": await_fps,
                    "audio": bool(stream.get("audio")),
                },
            }
            if not qc.ok:
                self.warnings.extend(f"{variant}: {error}" for error in qc.errors)
            self._progress(progress, "render", f"{variant} 完成：{final.name}", value + 0.2)

        result.videos = videos
        result.subtitles = subtitles
        result.qc = qc_all
        result.warnings = list(dict.fromkeys(self.warnings))
        manifest = {
            "schema_version": "2.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(time.time() - started, 2),
            "trace_id": execution.trace_id,
            "execution_trace_id": trace.metadata.execution_trace_id,
            "algorithm": trace.metadata.algorithm,
            "source_style": plan.source_style,
            "entry_point": execution.program.entry_point,
            "verified": plan.verified,
            "steps": len(trace.steps),
            "semantic_ops": [op.kind.value for op in execution.semantic_ops],
            "shared_trace": {
                "execution_sha256": plan.execution_sha256,
                "animation_sha256": plan.animation_sha256,
                "step_state_sha256": {str(item.step_id): item.state_sha256 for item in plan.steps},
            },
            "videos": {
                variant: {
                    "path": str(path),
                    "duration": probe_duration(path, self.settings),
                    "resolution": [plan.videos[i].width, plan.videos[i].height],
                    "fps": plan.videos[i].fps,
                    "subtitles": str(subtitles[variant]),
                    "render_plan": str(render_results[variant].plan_path),
                    "silent_video": str(render_results[variant].video),
                }
                for i, (variant, path) in enumerate(videos.items())
            },
            "teaching_plan": str(plan_path),
            "interactive_html": str(html),
            "execution_json": str(execution_path),
            "animation_events_json": str(animation_path),
            "complexity": plan.complexity.model_dump(mode="json"),
            "qc": qc_all,
            "warnings": result.warnings,
        }
        manifest_path = job_dir / "manifest.json"
        _write_json(manifest_path, manifest)
        result.manifest = manifest_path
        self._progress(progress, "done", f"M2 产物完成：{job_dir}", 1.0)
        return result
