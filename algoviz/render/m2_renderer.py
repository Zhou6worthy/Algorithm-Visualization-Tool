"""M2 渲染器：复用现有 Manim CLI，但使用 Two Sum 专用教学场景。"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings, get_settings
from ..media import probe_duration
from ..protocol.m2 import RenderPlan

log = logging.getLogger("algoviz.render.m2")

SCENE_TEMPLATE = """# 由 AlgoViz M2 自动生成，请勿手动修改
from algoviz.render.two_sum_scene import build_m2_scene_class

AlgoVizScene = build_m2_scene_class({plan_path!r})
AlgoVizScene.__module__ = __name__
"""


class M2RenderError(RuntimeError):
    pass


@dataclass
class M2RenderResult:
    video: Path
    duration: float
    log_path: Path
    command: list[str]
    media_dir: Path
    plan_path: Path


class M2Renderer:
    def __init__(self, settings: Settings | None = None, timeout: float = 2400.0) -> None:
        self.settings = settings or get_settings()
        self.timeout = timeout

    def render(
        self,
        plan: RenderPlan,
        work_dir: Path,
        *,
        resolution: tuple[int, int] | None = None,
        fps: int | None = None,
    ) -> M2RenderResult:
        work_dir = Path(work_dir).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        plan_path = work_dir / "render_plan.json"
        plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        scene_path = (work_dir / "scene.py").resolve()
        scene_path.write_text(SCENE_TEMPLATE.format(plan_path=str(plan_path.resolve())), encoding="utf-8")
        media_dir = work_dir / "media"
        log_path = work_dir / "manim.log"
        width, height = resolution or (plan.video.width, plan.video.height)
        frame_rate = fps or plan.video.fps
        command = [
            sys.executable,
            "-m",
            "manim",
            "render",
            str(scene_path),
            "AlgoVizScene",
            "--resolution",
            f"{width},{height}",
            "--fps",
            str(frame_rate),
            "--renderer",
            "cairo",
            "--disable_caching",
            "--media_dir",
            str(media_dir),
            "--output_file",
            "video_silent",
            "--format",
            "mp4",
            "-v",
            "ERROR",
        ]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        if str(self.settings.root) not in env.get("PYTHONPATH", ""):
            env["PYTHONPATH"] = str(self.settings.root) + os.pathsep + env.get("PYTHONPATH", "")
        log.info("M2 渲染开始：%s", " ".join(command))
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                cwd=str(work_dir),
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise M2RenderError(f"M2 渲染超时（{self.timeout:.0f}s）") from exc
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        log_path.write_text(output, encoding="utf-8")
        if proc.returncode != 0:
            tail = "\n".join(output.strip().splitlines()[-25:])
            raise M2RenderError(f"M2 渲染失败（exit {proc.returncode}）：\n{tail}")
        candidates = sorted(media_dir.glob("**/video_silent.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            raise M2RenderError(f"M2 渲染结束但未找到视频，日志：{log_path}")
        target = work_dir / "video_silent.mp4"
        shutil.copy2(candidates[0], target)
        duration = probe_duration(target, self.settings)
        return M2RenderResult(
            video=target,
            duration=duration,
            log_path=log_path,
            command=command,
            media_dir=media_dir,
            plan_path=plan_path,
        )
