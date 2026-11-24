"""从任务库生成视频清单（Markdown + JSON）。"""
from __future__ import annotations

import json
from pathlib import Path

from algoviz.config import get_settings
from algoviz.jobs.db import JobStore


def main() -> None:
    settings = get_settings()
    store = JobStore(settings)
    records = [r for r in store.list(limit=200) if r.status == "completed" and r.video_path]
    records.sort(key=lambda r: r.title)
    lines = [
        "# 演示视频清单",
        "",
        f"共 {len(records)} 个视频，位于 `output/videos/`。",
        "",
        "| # | 标题 | 算法 | 时长 | AI 讲解 | 算法校验 | 文件 |",
        "|---|---|---|---|---|---|---|",
    ]
    manifest = []
    for index, record in enumerate(records, start=1):
        video = Path(record.video_path) if record.video_path else None
        filename = video.name if video else "-"
        if record.ai_status == "used":
            ai_text = f"DeepSeek {record.ai_calls} 次"
        elif record.ai_status == "failed":
            ai_text = "调用失败"
        elif record.ai_status == "disabled":
            ai_text = "本地模板"
        elif record.ai_status == "unused":
            ai_text = "未触发"
        else:
            ai_text = "-"
        lines.append(
            f"| {index} | {record.title} | {record.algorithm or '-'} | "
            f"{(record.duration or 0):.1f}s | {ai_text} | {'✅' if record.verified else '❌'} | `{filename}` |"
        )
        manifest.append(
            {
                "job_id": record.id,
                "title": record.title,
                "algorithm": record.algorithm,
                "duration": record.duration,
                "verified": bool(record.verified),
                "ai_status": record.ai_status,
                "ai_calls": record.ai_calls,
                "ai_model": record.ai_model,
                "video": str(video) if video else None,
                "events": record.events_path,
                "subtitles": record.srt_path,
            }
        )
    output = settings.videos_dir / "MANIFEST.md"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (settings.videos_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"写入 {output}（{len(records)} 个视频）")
    for item in manifest:
        print(f"  {item['duration']:6.1f}s  {item['title']}  ->  {Path(item['video']).name}")


if __name__ == "__main__":
    main()
