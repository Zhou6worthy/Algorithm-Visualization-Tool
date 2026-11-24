"""单任务视频生成流水线：解析 → 执行追踪 → 讲解 → TTS → Manim → 音视频合成 → QC。"""
from __future__ import annotations

import json
import logging
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .ai.client import AIClient
from .ai.parser import TaskParser
from .algorithms.registry import ALGORITHMS, TaskValidationError, execute_task
from .config import Settings, get_settings
from .media import MediaError, concat_audio, make_silence, mux_video_audio, pad_audio, probe_duration
from .protocol.teaching import RenderOptions, ScenePlan, TaskSpec, TeachingScript
from .protocol.events import Trace
from .qc import QCReport, inspect_video
from .render.renderer import ManimRenderer, RenderError
from .script import build_teaching_script
from .subtitles import write_srt
from .timeline import build_scene_plan
from .tts import TTSEngine, estimate_duration

log = logging.getLogger("algoviz.pipeline")

ProgressCallback = Callable[[str, str, float], None]


class PipelineError(RuntimeError):
    pass


@dataclass
class PipelineResult:
    task: TaskSpec
    trace: Trace
    script: TeachingScript
    plan: ScenePlan
    final_video: Path
    srt_path: Path
    audio_path: Path | None
    duration: float
    qc: QCReport
    ai_usage: dict[str, object] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)


def _slugify(text: str, fallback: str = "video") -> str:
    text = re.sub(r'[\\/:*?"<>|\s]+', "_", text).strip("._")
    return (text or fallback)[:40]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


class Pipeline:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        ai: AIClient | None = None,
        parser: TaskParser | None = None,
        renderer: ManimRenderer | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.ai = ai or AIClient(self.settings)
        self.parser = parser or TaskParser(self.ai, self.settings)
        self.renderer = renderer or ManimRenderer(self.settings)

    # ------------------------------------------------------------------ 工具
    def _note(self, job_dir: Path, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        try:
            with (job_dir / "pipeline.log").open("a", encoding="utf-8") as handle:
                handle.write(f"[{stamp}] {message}\n")
        except OSError:
            pass
        log.info(message)

    def _progress(self, callback: ProgressCallback | None, status: str, message: str, value: float) -> None:
        log.info("[%s %.0f%%] %s", status, value * 100, message)
        if callback is not None:
            callback(status, message, value)

    # ------------------------------------------------------------------ 主流程
    def run(
        self,
        *,
        prompt: str | None = None,
        task: TaskSpec | None = None,
        job_dir: Path | None = None,
        progress: ProgressCallback | None = None,
    ) -> PipelineResult:
        started = time.time()
        if task is None and prompt is None:
            raise PipelineError("必须提供 prompt 或 task")
        job_dir = job_dir or self.settings.job_dir(f"task_{int(started * 1000)}")
        job_dir.mkdir(parents=True, exist_ok=True)
        warnings: list[str] = []
        self.ai.start_usage()

        self._progress(progress, "parsing", "解析输入，识别算法与参数", 0.03)
        if task is None:
            task = self.parser.parse(prompt or "")
        elif task.algorithm is None:
            if not task.prompt:
                raise PipelineError("任务没有指定算法，也没有提供自然语言描述")
            parsed = self.parser.parse(task.prompt, task.options)
            overrides = {"task_id": task.task_id, "options": task.options}
            if task.title:
                overrides["title"] = task.title
            task = parsed.model_copy(update=overrides)
        self._note(job_dir, f"任务：{task.algorithm or '待解析'} · {task.title or ''}")
        options = task.options
        self._note(
            job_dir,
            f"选项：tts={options.tts} theme={options.theme} quality={options.render_quality} "
            f"resolution={options.resolved_resolution()}",
        )

        self._progress(progress, "executing", "运行真实算法并逐步记录事件", 0.1)
        try:
            outcome = execute_task(task)
        except TaskValidationError as exc:
            if task.params:
                warnings.append(f"参数不合法，已回退到该算法的默认参数：{exc}")
                self._note(job_dir, warnings[-1])
                task = task.model_copy(update={"params": {}})
                outcome = execute_task(task)
            else:
                raise PipelineError(str(exc)) from exc
        trace = outcome.trace
        warnings.extend(outcome.warnings)
        if not trace.verified:
            warnings.append("算法结果未通过独立参考实现校验：" + "；".join(trace.verification_notes))
        events_path = job_dir / "events.json"
        events_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
        self._note(
            job_dir,
            f"算法执行完成：{len(trace.steps)} 个事件，verified={trace.verified}，"
            f"结果={trace.result.get('summary', '')}",
        )

        self._progress(progress, "rendering", "生成教学脚本与讲解文案", 0.2)
        algorithm = ALGORITHMS.get(trace.metadata.algorithm)
        if algorithm is None:
            raise PipelineError(f"内部错误：注册表缺少算法 {trace.metadata.algorithm}")
        script, script_warnings = build_teaching_script(trace, algorithm, options, self.ai)
        warnings.extend(script_warnings)
        ai_usage = self.ai.finish_usage()
        if ai_usage["status"] == "used":
            script.ai_credit = f"讲解：DeepSeek {ai_usage['model']}"
        elif ai_usage["status"] == "failed":
            script.ai_credit = "讲解：本地模板（大模型调用失败）"
        else:
            script.ai_credit = "讲解：本地模板"
        self._note(
            job_dir,
            f"大模型：{ai_usage['status']}，调用 {ai_usage['calls']} 次，"
            f"成功 {ai_usage['successes']} 次，模型 {ai_usage['model']}",
        )
        if ai_usage["status"] == "failed":
            warnings.append(f"大模型调用失败，已回退本地模板：{ai_usage.get('reason') or ''}")
        (job_dir / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")

        # 语音合成（失败自动降级，不阻塞视频）
        self._progress(progress, "rendering", "合成中文配音", 0.28)
        audio_files: list[Path | None] = []
        if options.tts and (options.tts_provider or self.settings.tts_provider) not in {"none", "silent"}:
            engine = TTSEngine(
                self.settings,
                provider=options.tts_provider or self.settings.tts_provider,
                voice=options.voice or self.settings.voice,
            )
            audio_dir = job_dir / "audio"
            results = engine.synthesize(
                [segment.narration for segment in script.segments], audio_dir, prefix="seg"
            )
            for segment, result in zip(script.segments, results):
                segment.audio_duration = result.duration
                segment.audio_path = str(result.path) if result.path else None
                if result.error:
                    warnings.append(f"配音（{result.provider}）：{result.error}")
                if result.path is None:
                    audio_files.append(None)
                else:
                    audio_files.append(result.path)
            providers = {result.provider for result in results}
            self._note(job_dir, f"配音完成：{len(results)} 段，provider={','.join(sorted(providers))}")
        else:
            for segment in script.segments:
                segment.audio_duration = estimate_duration(segment.narration)
                segment.audio_path = None
                audio_files.append(None)
            self._note(job_dir, "已关闭配音，生成静音视频（字幕仍会保留）")

        timeline = build_scene_plan(trace, script, options)
        warnings.extend(timeline.warnings)
        plan = timeline.plan
        if plan.total_duration <= 0:
            raise PipelineError("场景计划时长为 0，无法渲染")
        (job_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        self._note(
            job_dir,
            f"时间轴：{len(plan.script.segments)} 段，总时长 {plan.total_duration:.2f}s，"
            f"{len(plan.step_timings)} 个步骤时间点",
        )

        # Manim 渲染
        self._progress(progress, "rendering", "Manim 渲染动画（耗时较长）", 0.35)
        try:
            rendered = self.renderer.render(plan, job_dir)
        except RenderError as exc:
            raise PipelineError(str(exc)) from exc
        self._note(job_dir, f"Manim 渲染完成：{rendered.video}（{rendered.duration:.2f}s）")

        # 合成音轨
        self._progress(progress, "synthesizing", "拼接配音音轨并与视频合成", 0.78)
        audio_dir = job_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        narration_path: Path | None = None
        has_audio = any(path is not None for path in audio_files)
        if has_audio:
            padded: list[Path] = []
            for index, segment in enumerate(script.segments):
                target = audio_dir / f"pad_{index:02d}.wav"
                source = audio_files[index] if index < len(audio_files) else None
                try:
                    if source is not None and Path(source).exists():
                        pad_audio(source, target, segment.duration, self.settings)
                    else:
                        make_silence(target, segment.duration, self.settings)
                    padded.append(target)
                except MediaError as exc:
                    warnings.append(f"第 {index + 1} 段音轨处理失败：{exc}")
            if padded:
                raw = audio_dir / "narration_raw.wav"
                narration_path = job_dir / "narration.wav"
                try:
                    concat_audio(padded, raw, self.settings)
                    pad_audio(raw, narration_path, plan.total_duration, self.settings)
                    self._note(job_dir, f"配音音轨：{narration_path}（{probe_duration(narration_path, self.settings):.2f}s）")
                except MediaError as exc:
                    warnings.append(f"配音拼接失败：{exc}")
                    narration_path = None
        final_video = job_dir / "final.mp4"
        try:
            video_duration = probe_duration(rendered.video, self.settings)
        except MediaError:
            video_duration = plan.total_duration
        target_duration = min(plan.total_duration, video_duration) if video_duration > 0 else plan.total_duration
        if narration_path is not None:
            try:
                mux_video_audio(rendered.video, narration_path, final_video, target_duration, self.settings)
            except MediaError as exc:
                raise PipelineError(f"音视频合成失败：{exc}") from exc
        else:
            shutil.copy2(rendered.video, final_video)
        final_duration = probe_duration(final_video, self.settings)

        self._progress(progress, "validating", "导出字幕并执行质量检查", 0.9)
        srt_path = write_srt(plan.subtitles, job_dir / "subtitles.srt")
        qc = inspect_video(
            final_video,
            expected_duration=plan.total_duration,
            expected_resolution=tuple(plan.resolution),
            expected_fps=plan.fps,
            expect_audio=has_audio,
            verified=trace.verified,
            settings=self.settings,
            work_dir=job_dir,
        )
        _write_json(job_dir / "qc.json", qc.as_dict())
        if qc.warnings:
            warnings.extend(qc.warnings)
        if not qc.ok:
            raise PipelineError("质量检查未通过：" + "；".join(qc.errors))

        # 发布到 videos 目录
        published = self.settings.videos_dir / f"{_slugify(script.title or trace.metadata.algorithm)}_{job_dir.name}.mp4"
        shutil.copy2(final_video, published)
        artifacts = {
            "final_video": str(published),
            "job_video": str(final_video),
            "events": str(events_path),
            "script": str(job_dir / "script.json"),
            "plan": str(job_dir / "plan.json"),
            "subtitles": str(srt_path),
            "qc": str(job_dir / "qc.json"),
        }
        if narration_path is not None:
            artifacts["narration"] = str(narration_path)
        if (job_dir / "manim.log").exists():
            artifacts["manim_log"] = str(job_dir / "manim.log")
        meta = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(time.time() - started, 2),
            "task": task.model_dump(mode="json"),
            "trace": {
                "algorithm": trace.metadata.algorithm,
                "title": script.title,
                "steps": len(trace.steps),
                "verified": trace.verified,
            },
            "duration": final_duration,
            "planned_duration": plan.total_duration,
            "warnings": warnings,
            "artifacts": artifacts,
            "ai": self.ai.describe(),
            "ai_usage": ai_usage,
        }
        _write_json(job_dir / "meta.json", meta)
        self._note(job_dir, f"任务完成：{published}（{final_duration:.2f}s，耗时 {time.time() - started:.1f}s）")
        self._progress(progress, "validating", "视频生成完成", 1.0)
        return PipelineResult(
            task=task,
            trace=trace,
            script=script,
            plan=plan,
            final_video=published,
            srt_path=srt_path,
            audio_path=narration_path,
            duration=final_duration,
            qc=qc,
            ai_usage=ai_usage,
            warnings=warnings,
            artifacts=artifacts,
        )
