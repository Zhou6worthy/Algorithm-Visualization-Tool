"""命令行入口：algoviz generate / batch / algorithms / serve / doctor。"""
from __future__ import annotations

import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Optional

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from . import __version__
from .ai.client import AIClient
from .ai.settings_store import mask_key
from .algorithms.registry import list_algorithms
from .batch import default_render_options, load_batch
from .config import get_settings
from .jobs.db import JobStore
from .jobs.worker import BatchRunner
from .pipeline import Pipeline
from .protocol.teaching import RenderOptions, TaskSpec

app = typer.Typer(add_completion=False, help="AlgoViz · AI 算法教学视频批量生成工厂")
console = Console()


def _apply_overrides(
    options: RenderOptions,
    *,
    quality: str | None = None,
    tts: bool | None = None,
    voice: str | None = None,
    theme: str | None = None,
    steps_per_segment: int | None = None,
) -> RenderOptions:
    data = options.model_dump()
    if quality:
        data["render_quality"] = quality
        if quality == "low":
            data["resolution"] = (854, 480)
        elif quality == "medium":
            data["resolution"] = (1280, 720)
        else:
            data["resolution"] = (1920, 1080)
    if tts is not None:
        data["tts"] = tts
    if voice:
        data["voice"] = voice
    if theme:
        data["theme"] = theme
    if steps_per_segment:
        data["steps_per_segment"] = steps_per_segment
    return RenderOptions.model_validate(data)


@app.command()
def generate(
    prompt: Optional[str] = typer.Argument(None, help="自然语言 / 伪代码描述；也可以只给 --algorithm"),
    algorithm: Optional[str] = typer.Option(None, "--algorithm", "-a", help="算法 key，例如 quick_sort"),
    params: Optional[str] = typer.Option(None, "--params", help="参数字典 JSON，例如 '{\"array\":[5,3,8]}'"),
    array: Optional[str] = typer.Option(None, "--array", help="数组，例如 \"5,3,8,1\"（排序/查找）"),
    target: Optional[str] = typer.Option(None, "--target", help="查找目标值"),
    values: Optional[str] = typer.Option(None, "--values", help="树节点序列，例如 \"8,3,10\""),
    title: Optional[str] = typer.Option(None, "--title", help="视频标题"),
    quality: str = typer.Option("high", "--quality", "-q", help="high / medium / low"),
    tts: bool = typer.Option(True, "--tts/--no-tts", help="是否生成中文配音"),
    voice: Optional[str] = typer.Option(None, "--voice"),
    theme: Optional[str] = typer.Option(None, "--theme", help="dark / light"),
    steps_per_segment: int = typer.Option(3, "--steps-per-segment", help="每个执行讲解片段包含的步骤数"),
) -> None:
    """生成单个算法教学视频。"""
    if not prompt and not algorithm:
        console.print("[red]请提供自然语言描述，或用 --algorithm 指定算法。[/red]")
        raise typer.Exit(code=2)
    settings = get_settings()
    if settings.ai_available:
        console.print(f"[cyan]大模型：[/cyan]DeepSeek {settings.deepseek_model} 已启用")
    else:
        reason = "未配置 DEEPSEEK_API_KEY" if not settings.deepseek_api_key else "AI 模式为 off"
        console.print(f"[yellow]大模型：未启用（{reason}），本次使用本地模板讲解；可用 algoviz ai-check 检查配置[/yellow]")
    options = _apply_overrides(
        default_render_options(settings),
        quality=quality,
        tts=tts,
        voice=voice,
        theme=theme,
        steps_per_segment=steps_per_segment,
    )
    param_data: dict = {}
    if params:
        param_data.update(json.loads(params))
    if array:
        param_data["array"] = array
    if target:
        param_data["target"] = target
    if values:
        param_data["values"] = values
    task = TaskSpec(
        algorithm=algorithm,
        params=param_data,
        prompt=prompt,
        title=title,
        source="preset" if algorithm and not prompt else "natural_language",
        options=options,
    )
    store = JobStore(settings)
    runner = BatchRunner(store=store, pipeline=Pipeline(settings), workers=1, retries=settings.retries)
    record = store.create(task, title=title, algorithm=algorithm)
    console.print(f"[bold]任务[/bold] {record.id} · {record.title}")
    summaries = runner.run([record.id])
    result = summaries[0] if summaries else None
    if result and result.status == "completed":
        console.print(f"[green]视频已生成：[/green]{result.video_path}")
        console.print(f"时长 {result.duration:.1f}s，算法校验：{result.verified}")
        if result.ai_status == "used":
            console.print(
                f"[green]大模型：[/green]✅ 已调用 DeepSeek（{result.ai_model}，{result.ai_calls} 次成功）"
            )
        elif result.ai_status == "failed":
            console.print("[red]大模型：[/red]❌ 调用失败，已回退本地模板；运行 algoviz ai-check 查看原因")
        elif result.ai_status == "disabled":
            console.print("[yellow]大模型：[/yellow]⚠️ 未调用（未配置 Key 或 AI 关闭），本次使用本地模板")
        else:
            console.print(f"[yellow]大模型：[/yellow]未触发（{result.ai_status or '未知'}），使用本地模板")
    else:
        console.print(f"[red]失败：[/red]{result.error if result else '未知错误'}")
        raise typer.Exit(code=1)


@app.command()
def batch(
    file: Path = typer.Argument(..., exists=True, dir_okay=False, help="批量任务 JSON 文件"),
    workers: Optional[int] = typer.Option(None, "--workers", "-w", help="并发线程数"),
    retries: Optional[int] = typer.Option(None, "--retries", help="单任务失败重试次数"),
    quality: Optional[str] = typer.Option(None, "--quality", "-q", help="覆盖画质 high/medium/low"),
    tts: Optional[bool] = typer.Option(None, "--tts/--no-tts", help="覆盖是否配音"),
    steps_per_segment: Optional[int] = typer.Option(None, "--steps-per-segment"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只解析和打印任务，不执行"),
) -> None:
    """批量生成：读取任务文件，并发执行，失败单任务重试。"""
    settings = get_settings()
    batch_name, tasks = load_batch(file, settings)
    if quality or tts is not None or steps_per_segment:
        tasks = [
            task.model_copy(
                update={
                    "options": _apply_overrides(
                        task.options,
                        quality=quality,
                        tts=tts,
                        steps_per_segment=steps_per_segment,
                    )
                }
            )
            for task in tasks
        ]
    table = Table(title=f"批次 {batch_name} · {len(tasks)} 个任务", box=box.SIMPLE)
    table.add_column("#", justify="right")
    table.add_column("算法")
    table.add_column("标题")
    table.add_column("输入")
    for index, task in enumerate(tasks, start=1):
        preview = task.algorithm or (task.prompt or "")[:40]
        input_preview = json.dumps(task.params, ensure_ascii=False)[:60] if task.params else "-"
        table.add_row(str(index), task.algorithm or "AI 解析", task.title or "-", input_preview or preview)
    console.print(table)
    if dry_run:
        return
    store = JobStore(settings)
    store.recover_interrupted()
    runner = BatchRunner(
        store=store,
        pipeline=Pipeline(settings),
        workers=workers or settings.workers,
        retries=retries if retries is not None else settings.retries,
    )
    batch_id = f"{batch_name}_{uuid.uuid4().hex[:6]}"
    records = runner.create_jobs(tasks, batch_id=batch_id)
    console.print(f"[bold]批次 {batch_id}[/bold]：{len(records)} 个任务，并发 {runner.workers}，重试 {runner.retries}")
    summaries = runner.run([record.id for record in records])
    completed = [item for item in summaries if item.status == "completed"]
    failed = [item for item in summaries if item.status != "completed"]
    console.print(
        f"\n[bold]完成 {len(completed)} / {len(summaries)}[/bold]，失败 {len(failed)}；"
        f"视频目录：{settings.videos_dir}"
    )
    if failed:
        for item in failed:
            console.print(f"[red]{item.job_id}[/red] {item.title}: {item.error}")
        raise typer.Exit(code=1)


@app.command()
def algorithms() -> None:
    """列出内置算法及其参数。"""
    table = Table(title="AlgoViz 内置算法", box=box.SIMPLE)
    table.add_column("key", style="cyan")
    table.add_column("标题")
    table.add_column("类别")
    table.add_column("复杂度")
    table.add_column("默认参数", overflow="fold")
    for spec in list_algorithms():
        table.add_row(
            spec.key,
            spec.title,
            spec.category,
            f"{spec.time_complexity} / {spec.space_complexity}",
            json.dumps(spec.defaults, ensure_ascii=False),
        )
    console.print(table)


@app.command()
def jobs(
    limit: int = typer.Option(30, "--limit"),
    status: Optional[str] = typer.Option(None, "--status"),
) -> None:
    """查看任务列表。"""
    settings = get_settings()
    store = JobStore(settings)
    records = store.list(status=status, limit=limit)
    table = Table(box=box.SIMPLE)
    table.add_column("id", style="cyan")
    table.add_column("标题")
    table.add_column("状态")
    table.add_column("进度")
    table.add_column("时长")
    table.add_column("AI 讲解")
    table.add_column("视频")
    for record in records:
        if record.ai_status == "used":
            ai_text = f"DeepSeek {record.ai_calls}次"
        elif record.ai_status == "failed":
            ai_text = "调用失败"
        elif record.ai_status == "disabled":
            ai_text = "本地模板"
        elif record.ai_status == "unused":
            ai_text = "未触发"
        else:
            ai_text = "-"
        table.add_row(
            record.id,
            record.title,
            record.status,
            f"{record.progress:.0%}",
            f"{record.duration:.1f}s" if record.duration else "-",
            ai_text,
            "✓" if record.video_path and Path(record.video_path).exists() else "-",
        )
    console.print(table)


@app.command()
def doctor() -> None:
    """检查运行环境（Python / Manim / FFmpeg / 字体 / 大模型 / TTS）。"""
    settings = get_settings()
    table = Table(title="AlgoViz 环境检查", box=box.SIMPLE)
    table.add_column("项目")
    table.add_column("状态")
    table.add_column("说明")

    def add(name: str, ok: bool, detail: str) -> None:
        table.add_row(name, "[green]OK[/green]" if ok else "[red]缺失[/red]", detail)

    add("Python", sys.version_info >= (3, 10), sys.version.split()[0])
    try:
        import manim

        add("Manim CE", True, f"v{manim.__version__}")
    except Exception as exc:  # noqa: BLE001
        add("Manim CE", False, str(exc))
    add("FFmpeg", bool(shutil.which("ffmpeg")), shutil.which("ffmpeg") or "未找到 ffmpeg")
    add("FFprobe", bool(shutil.which("ffprobe")), shutil.which("ffprobe") or "未找到 ffprobe")
    font_ok = Path(os.environ.get("WINDIR", r"C:\Windows")) .joinpath("Fonts", "msyh.ttc").exists()
    add("中文字体", font_ok or sys.platform != "win32", settings.cn_font)
    try:
        import edge_tts  # noqa: F401

        add("Edge TTS", True, settings.voice)
    except Exception as exc:  # noqa: BLE001
        add("Edge TTS", False, str(exc))
    add(
        "DeepSeek",
        settings.ai_available,
        f"{settings.deepseek_model} @ {settings.deepseek_base_url}"
        + (
            f"（Key {mask_key(settings.deepseek_api_key)}）"
            if settings.deepseek_api_key
            else "（未配置 DEEPSEEK_API_KEY，将使用本地模板；可用 algoviz ai-check 检查）"
        ),
    )
    writable = os.access(settings.output_dir, os.W_OK)
    add("输出目录", writable, str(settings.output_dir))
    console.print(table)


@app.command("ai-check")
def ai_check() -> None:
    """测试 DeepSeek Key 是否真的可用。"""
    settings = get_settings()
    console.print(f"配置文件：{settings.env_path}")
    console.print(
        f"API Key：{mask_key(settings.deepseek_api_key) or '未配置'} · "
        f"模型：{settings.deepseek_model} · 模式：{settings.ai_mode}"
    )
    client = AIClient(settings)
    if not client.available:
        reason = "未配置 DEEPSEEK_API_KEY" if not settings.deepseek_api_key else "ALGOVIZ_AI_MODE=off"
        console.print(f"[yellow]未启用大模型：{reason}[/yellow]")
        console.print("可运行 [bold]algoviz serve[/bold] 打开 GUI，在「AI 设置」中填写 Key。")
        raise typer.Exit(code=2)
    with console.status("正在请求 DeepSeek…"):
        result = client.test_connection()
    if result["ok"]:
        console.print(f"[green]连接成功[/green] · 模型 {result['model']} · 延迟 {result['latency_ms']}ms")
        console.print(f"返回：{result['response']}")
    else:
        console.print(f"[red]连接失败[/red]：{result['error']}")
        console.print("请检查 Key、Base URL、网络或账户余额；调用失败时视频仍会使用本地模板生成。")
        raise typer.Exit(code=1)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    """启动 FastAPI 服务。"""
    import uvicorn

    from .api.app import create_app

    uvicorn.run(create_app(), host=host, port=port, log_level="info")


@app.command()
def version() -> None:
    console.print(f"AlgoViz {__version__}")


if __name__ == "__main__":
    app()
