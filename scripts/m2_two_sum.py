"""M2 验收脚本：函数版 + LeetCode 类版 Two Sum 教学闭环。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from algoviz.config import get_settings
from algoviz.teaching.two_sum_pipeline import TwoSumTeachingPipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Two Sum M2 教学视频与 HTML")
    parser.add_argument("--m1-root", default="output/m1", help="M1 产物根目录")
    parser.add_argument("--output-root", default="output/m2", help="M2 输出根目录")
    parser.add_argument("--forms", default="function,class", help="function,class")
    parser.add_argument("--no-tts", action="store_true", help="关闭 TTS（仅调试）")
    parser.add_argument("--voice", default=None, help="覆盖中文音色")
    args = parser.parse_args()

    m1_root = Path(args.m1_root)
    output_root = Path(args.output_root)
    forms = [item.strip() for item in args.forms.split(",") if item.strip()]
    settings = get_settings()
    summaries = []
    for form in forms:
        source_dir = m1_root / ("two_sum_function" if form == "function" else "two_sum_class")
        execution = source_dir / "execution.json"
        animation = source_dir / "animation_events.json"
        if not execution.exists() or not animation.exists():
            raise SystemExit(f"缺少 M1 产物：{execution} / {animation}")
        job_dir = output_root / ("two_sum_function" if form == "function" else "two_sum_class")
        print(f"\n=== M2 {form} -> {job_dir} ===")
        pipeline = TwoSumTeachingPipeline(settings=settings, tts=not args.no_tts, voice=args.voice)
        result = pipeline.run(
            execution_src=execution,
            animation_src=animation,
            job_dir=job_dir,
        )
        entry = {
            "form": form,
            "job_dir": str(job_dir),
            "trace_id": result.plan.trace_id,
            "steps": len(result.plan.steps),
            "html": str(result.html) if result.html else None,
            "teaching_plan": str(job_dir / "teaching_plan.json"),
            "overview": str(result.videos.get("overview", "")),
            "step_by_step": str(result.videos.get("step_by_step", "")),
            "overview_srt": str(result.subtitles.get("overview", "")),
            "step_by_step_srt": str(result.subtitles.get("step_by_step", "")),
            "qc": result.qc,
            "warnings": result.warnings,
        }
        summaries.append(entry)
        print(json.dumps(entry, ensure_ascii=False, indent=2))
    summary_path = output_root / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    merged: list[dict] = []
    if summary_path.exists():
        try:
            existing = json.loads(summary_path.read_text(encoding="utf-8"))
            if isinstance(existing, list):
                merged = [item for item in existing if item.get("form") not in {entry["form"] for entry in summaries}]
        except (json.JSONDecodeError, OSError):
            merged = []
    merged.extend(summaries)
    summary_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nM2 summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
