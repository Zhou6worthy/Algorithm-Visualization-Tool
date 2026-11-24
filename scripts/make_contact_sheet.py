"""从最终视频生成一张 5x2 预览拼图。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from algoviz.config import get_settings

settings = get_settings()
manifest = sorted(settings.videos_dir.glob("*.mp4"))
frames_dir = settings.videos_dir / "_thumbs"
frames_dir.mkdir(exist_ok=True)
font_path = Path(r"C:\Windows\Fonts\msyh.ttc")
font = ImageFont.truetype(str(font_path), 22) if font_path.exists() else ImageFont.load_default()
font_small = ImageFont.truetype(str(font_path), 17) if font_path.exists() else font

thumb_w, thumb_h = 480, 270
label_h = 52
cols, rows = 5, 2
canvas = Image.new("RGB", (thumb_w * cols, (thumb_h + label_h) * rows), (11, 18, 32))
draw = ImageDraw.Draw(canvas)
for index, video in enumerate(manifest[:10]):
    duration = float(
        subprocess.run(
            [
                settings.ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(video),
            ],
            capture_output=True,
            text=True,
        ).stdout.strip()
        or 60
    )
    stamp = max(2.0, duration * 0.35)
    frame_path = frames_dir / f"{index:02d}.png"
    subprocess.run(
        [
            settings.ffmpeg,
            "-y",
            "-v",
            "error",
            "-ss",
            f"{stamp:.2f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            f"scale={thumb_w}:{thumb_h}",
            str(frame_path),
        ],
        check=True,
    )
    frame = Image.open(frame_path).convert("RGB")
    x = (index % cols) * thumb_w
    y = (index // cols) * (thumb_h + label_h)
    canvas.paste(frame, (x, y))
    title = video.stem.split("_")[0][:26]
    draw.text((x + 10, y + thumb_h + 8), title, fill=(232, 238, 249), font=font)
    draw.text((x + 10, y + thumb_h + 30), f"{duration:.0f}s · 1080p", fill=(154, 169, 194), font=font_small)
output = settings.videos_dir / "contact_sheet.png"
canvas.save(output, quality=92)
print(output)
