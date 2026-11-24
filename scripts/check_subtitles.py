import json
from pathlib import Path

from algoviz.timeline import wrap_subtitle

for directory in sorted(Path("output/jobs").iterdir()):
    plan_path = directory / "plan.json"
    if not plan_path.exists():
        continue
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    cues = plan["subtitles"]
    two = sum(1 for cue in cues if "\n" in wrap_subtitle(cue["text"], 34, 2))
    print(f"{directory.name:26s} cues={len(cues):2d} two_line={two:2d}")
