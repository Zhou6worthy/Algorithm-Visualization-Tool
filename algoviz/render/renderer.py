"""Manim 渲染器：生成场景包装文件，调用 manim CLI，产出无声视频。"""
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
from ..protocol.teaching import ScenePlan

log = logging.getLogger("algoviz.render")

SCENE_TEMPLATE = """# 由 AlgoViz 自动生成，请勿手动修改
from algoviz.render.scene import build_scene_class

AlgoVizScene = build_scene_class({plan_path!r})
AlgoVizScene.__module__ = __name__
"""


class RenderError(RuntimeError):
    pass


@dataclass
class RenderResult:
    video: Path
    duration: float
    log_path: Path
    command: list[str]
    media_dir: Path


class ManimRenderer:
    def __init__(self, settings: Settings | None = None, timeout: float = 3600.0) -> None:
        self.settings = settings or get_settings()
        self.timeout = timeout

    def render(self, plan: ScenePlan, work_dir: Path) -> RenderResult:
        work_dir.mkdir(parents=True, exist_ok=True)
        plan_path = work_dir / "plan.json"
        plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        scene_path = work_dir / "scene.py"
        scene_path.write_text(SCENE_TEMPLATE.format(plan_path=str(plan_path)), encoding="utf-8")
        media_dir = work_dir / "media"
        log_path = work_dir / "manim.log"
        width, height = plan.resolution
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
            str(plan.fps),
            "--renderer",
            "cairo",
            "--disable_caching",
            "--media_dir",
            str(media_dir),
            "--output_file",
            "video_silent",
            "-v",
            "ERROR",
        ]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        if str(self.settings.root) not in env.get("PYTHONPATH", ""):
            env["PYTHONPATH"] = str(self.settings.root) + os.pathsep + env.get("PYTHONPATH", "")
        log.info("开始渲染：%s", " ".join(command))
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
            raise RenderError(f"Manim 渲染超时（{self.timeout:.0f}s）") from exc
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        log_path.write_text(output, encoding="utf-8")
        if proc.returncode != 0:
            tail = "\n".join(line for line in output.strip().splitlines()[-20:])
            raise RenderError(f"Manim 渲染失败（exit {proc.returncode}）：\n{tail}")
        candidates = sorted(media_dir.glob("**/video_silent.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            raise RenderError(f"Manim 渲染结束但未找到输出视频，日志：{log_path}")
        target = work_dir / "video_silent.mp4"
        shutil.copy2(candidates[0], target)
        duration = probe_duration(target, self.settings)
        log.info("渲染完成：%s（%.1fs）", target, duration)
        return RenderResult(
            video=target,
            duration=duration,
            log_path=log_path,
            command=command,
            media_dir=media_dir,
        )
