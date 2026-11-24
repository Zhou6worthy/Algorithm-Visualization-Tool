"""全局配置：环境变量 + 字体/工具链探测。"""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CN_FONT_CANDIDATES = [
    "Microsoft YaHei",
    "Microsoft YaHei UI",
    "Source Han Sans SC",
    "Noto Sans CJK SC",
    "PingFang SC",
    "SimHei",
    "DengXian",
]
CODE_FONT_CANDIDATES = ["Cascadia Mono", "Consolas", "JetBrains Mono", "Courier New"]


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _float(value: str | None, default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _font_available(font: str) -> bool:
    """Windows 上通过字体目录粗查；其它平台默认可用（Pango/fontconfig 会处理）。"""
    if sys.platform != "win32":
        return True
    fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    if not fonts.exists():
        return True
    needle = font.lower().replace(" ", "")
    for f in fonts.iterdir():
        stem = f.stem.lower().replace(" ", "")
        if needle in stem:
            return True
    # 常见字体文件别名
    aliases = {
        "microsoftyahei": ("msyh", "microsoftyahei"),
        "microsoftyaheiui": ("msyh",),
        "simhei": ("simhei",),
        "dengxian": ("deng",),
        "consolas": ("consola",),
        "cascadiamono": ("cascadia",),
        "couriernew": ("cour",),
    }
    for prefix in aliases.get(needle, ()):
        for f in fonts.iterdir():
            if f.stem.lower().startswith(prefix):
                return True
    return False


def detect_font(candidates: list[str], fallback: str = "sans-serif") -> str:
    for font in candidates:
        if _font_available(font):
            return font
    return fallback


@dataclass
class Settings:
    root: Path = ROOT
    output_dir: Path = field(default_factory=lambda: ROOT / os.getenv("ALGOVIZ_OUTPUT", "output"))
    env_path: Path = field(default_factory=lambda: Path(os.getenv("ALGOVIZ_ENV_FILE", str(ROOT / ".env"))))
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    ai_mode: str = os.getenv("ALGOVIZ_AI_MODE", "auto").lower()
    tts_provider: str = os.getenv("ALGOVIZ_TTS_PROVIDER", "edge").lower()
    voice: str = os.getenv("ALGOVIZ_VOICE", "zh-CN-XiaoxiaoNeural")
    tts_rate: str = os.getenv("ALGOVIZ_TTS_RATE", "+0%")
    theme: str = os.getenv("ALGOVIZ_THEME", "dark")
    resolution: tuple[int, int] = (1920, 1080)
    fps: int = 30
    max_seconds: float = 240.0
    workers: int = 2
    retries: int = 1
    render_quality: str = os.getenv("ALGOVIZ_RENDER_QUALITY", "high").lower()
    cn_font: str = ""
    code_font: str = ""
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"

    def __post_init__(self) -> None:
        res = os.getenv("ALGOVIZ_RESOLUTION", "")
        if "x" in res.lower():
            try:
                w, h = res.lower().split("x")
                self.resolution = (int(w), int(h))
            except ValueError:
                pass
        if self.render_quality == "low":
            self.resolution = (854, 480)
        elif self.render_quality == "medium":
            self.resolution = (1280, 720)
        self.fps = _int(os.getenv("ALGOVIZ_FPS"), 30)
        self.max_seconds = _float(os.getenv("ALGOVIZ_MAX_SECONDS"), 240.0)
        self.workers = max(1, _int(os.getenv("ALGOVIZ_WORKERS"), 2))
        self.retries = max(0, _int(os.getenv("ALGOVIZ_RETRIES"), 1))
        self.output_dir = Path(os.getenv("ALGOVIZ_OUTPUT", str(self.output_dir)))
        if not self.output_dir.is_absolute():
            self.output_dir = ROOT / self.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if not self.env_path.is_absolute():
            self.env_path = ROOT / self.env_path
        self.cn_font = os.getenv("ALGOVIZ_CN_FONT") or detect_font(CN_FONT_CANDIDATES)
        self.code_font = os.getenv("ALGOVIZ_CODE_FONT") or detect_font(CODE_FONT_CANDIDATES, "monospace")
        self.ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe = shutil.which("ffprobe") or "ffprobe"

    @property
    def db_path(self) -> Path:
        return self.output_dir / "tasks.sqlite3"

    @property
    def workbench_db_path(self) -> Path:
        return self.output_dir / "workbench.sqlite3"

    @property
    def videos_dir(self) -> Path:
        d = self.output_dir / "videos"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def jobs_dir(self) -> Path:
        d = self.output_dir / "jobs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def ai_available(self) -> bool:
        return self.ai_mode != "off" and bool(self.deepseek_api_key)

    def job_dir(self, job_id: str) -> Path:
        d = self.jobs_dir / job_id
        d.mkdir(parents=True, exist_ok=True)
        return d


_settings: Settings | None = None


def get_settings(refresh: bool = False) -> Settings:
    global _settings
    if _settings is None or refresh:
        _settings = Settings()
    return _settings
