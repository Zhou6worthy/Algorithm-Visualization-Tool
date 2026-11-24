"""快速渲染单个算法的调试视频：python scripts/render_algo.py tree_inorder [low|medium] [--audio]"""
from __future__ import annotations

import sys
from pathlib import Path

from algoviz.ai.client import AIClient
from algoviz.algorithms.registry import ALGORITHMS, execute_task
from algoviz.config import get_settings
from algoviz.protocol.teaching import RenderOptions, TaskSpec
from algoviz.render.renderer import ManimRenderer
from algoviz.script import build_teaching_script
from algoviz.timeline import build_scene_plan
from algoviz.tts import estimate_duration

algorithm = sys.argv[1] if len(sys.argv) > 1 else "tree_inorder"
quality = sys.argv[2] if len(sys.argv) > 2 else "low"
settings = get_settings()
options = RenderOptions(render_quality=quality, tts=False)
task = TaskSpec(algorithm=algorithm)
outcome = execute_task(task)
script, warnings = build_teaching_script(
    outcome.trace, ALGORITHMS[algorithm], options, AIClient(settings)
)
for seg in script.segments:
    seg.audio_duration = min(2.5, estimate_duration(seg.narration))
result = build_scene_plan(outcome.trace, script, options)
work = settings.output_dir / f"_render_{algorithm}"
renderer = ManimRenderer(settings)
rendered = renderer.render(result.plan, work)
print(f"OK {algorithm} steps={len(outcome.trace.steps)} segments={len(script.segments)} "
      f"duration={result.plan.total_duration:.1f} video={rendered.duration:.1f} path={rendered.video}")
