from __future__ import annotations

from contextlib import asynccontextmanager
import html
import threading
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..ai.client import AIClient
from ..ai.settings_store import ai_public_settings, update_ai_settings
from ..algorithms.registry import list_algorithms
from ..batch import default_render_options
from ..config import Settings, get_settings
from ..jobs.db import JobStore
from ..jobs.worker import BatchRunner
from ..pipeline import Pipeline
from ..protocol.teaching import RenderOptions, TaskSpec
from ..workbench.api import create_workbench_router
from ..workbench.service import WorkbenchRunService
from ..workbench.store import WorkbenchStore


class GenerateRequest(BaseModel):
    prompt: str | None = None
    algorithm: str | None = None
    params: dict = Field(default_factory=dict)
    title: str | None = None
    options: RenderOptions | None = None


class BatchRequest(BaseModel):
    tasks: list[TaskSpec] = Field(min_length=1)
    batch_name: str | None = None


class AISettingsUpdate(BaseModel):
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None
    mode: str | None = None
    clear_key: bool = False


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = JobStore(settings)
    store.recover_interrupted()
    pipeline = Pipeline(settings)
    runner = BatchRunner(
        store=store,
        pipeline=pipeline,
        workers=settings.workers,
        retries=settings.retries,
    )
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        workbench_service.close()
        workbench_store.close()

    app = FastAPI(
        title="AlgoViz · AI 算法可视化视频工厂",
        version=__version__,
        description="算法执行追踪 → 课堂演示 / Manim 动画 → 中文配音字幕 → MP4",
        lifespan=lifespan,
    )
    app.state.store = store
    app.state.runner = runner
    app.state.settings = settings
    app.state.ai_lock = threading.Lock()
    app.state.last_ai_test = None

    workbench_store = WorkbenchStore(settings.workbench_db_path)
    workbench_store.recover_interrupted()
    workbench_service = WorkbenchRunService(workbench_store, settings, max_workers=1)
    app.state.workbench_store = workbench_store
    app.state.workbench_service = workbench_service
    app.include_router(create_workbench_router(workbench_store, workbench_service))

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "ai": ai_public_settings(settings, pipeline.ai, last_test=app.state.last_ai_test),
            "tts": settings.tts_provider,
            "workers": runner.workers,
            "stats": store.stats(),
        }

    @app.get("/api/v1/settings/ai")
    def get_ai_settings() -> dict:
        return ai_public_settings(settings, pipeline.ai, last_test=app.state.last_ai_test)

    @app.post("/api/v1/settings/ai")
    def set_ai_settings(request: AISettingsUpdate) -> dict:
        with app.state.ai_lock:
            try:
                result = update_ai_settings(
                    settings,
                    pipeline.ai,
                    api_key=request.api_key,
                    model=request.model,
                    base_url=request.base_url,
                    mode=request.mode,
                    clear_key=request.clear_key,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            parser_ai = getattr(pipeline.parser, "ai", None)
            if parser_ai is not None and parser_ai is not pipeline.ai:
                parser_ai.settings = settings
                parser_ai.reset_connection()
            app.state.last_ai_test = None
            return {
                **result,
                "last_test": None,
                "message": "配置已保存到 .env，并立即生效",
            }

    @app.post("/api/v1/ai/test")
    def test_ai() -> dict:
        with app.state.ai_lock:
            client = AIClient(settings)
            result = client.test_connection()
            app.state.last_ai_test = result
            return result

    @app.get("/api/v1/algorithms")
    def algorithms() -> list[dict]:
        return [
            {
                "key": spec.key,
                "title": spec.title,
                "category": spec.category,
                "aliases": list(spec.aliases),
                "defaults": spec.defaults,
                "complexity": {
                    "time": spec.time_complexity,
                    "space": spec.space_complexity,
                    "note": spec.complexity_note,
                },
            }
            for spec in list_algorithms()
        ]

    @app.post("/api/v1/generate")
    def generate(request: GenerateRequest, background: BackgroundTasks) -> dict:
        if not request.prompt and not request.algorithm:
            raise HTTPException(status_code=422, detail="请提供 prompt 或 algorithm")
        options = request.options or default_render_options(settings)
        task = TaskSpec(
            algorithm=request.algorithm,
            params=request.params,
            prompt=request.prompt,
            title=request.title,
            source="preset" if request.algorithm and not request.prompt else "natural_language",
            options=options,
        )
        record = store.create(task, title=request.title, algorithm=request.algorithm)
        background.add_task(runner.run, [record.id])
        return {"job": record.as_dict(), "status_url": f"/api/v1/jobs/{record.id}"}

    @app.post("/api/v1/batch")
    def create_batch(request: BatchRequest) -> dict:
        batch_id = request.batch_name or f"batch_{uuid.uuid4().hex[:8]}"
        records = runner.create_jobs(request.tasks, batch_id=batch_id)
        batch_runner = runner
        import threading

        thread = threading.Thread(
            target=lambda: batch_runner.run([record.id for record in records]),
            name=f"batch-{batch_id}",
            daemon=True,
        )
        thread.start()
        return {
            "batch_id": batch_id,
            "jobs": [record.as_dict() for record in records],
        }

    @app.get("/api/v1/jobs")
    def list_jobs(
        status: str | None = None,
        batch_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        return [record.as_dict() for record in store.list(status=status, batch_id=batch_id, limit=limit)]

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        record = store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return record.as_dict(include_input=True)

    @app.post("/api/v1/jobs/{job_id}/retry")
    def retry_job(job_id: str) -> dict:
        record = store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        try:
            task = record.task()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=f"任务参数无法恢复：{exc}") from exc
        new_record = store.create(
            task,
            batch_id=record.batch_id,
            title=record.title,
            algorithm=record.algorithm or task.algorithm,
        )
        threading.Thread(
            target=runner.run,
            args=([new_record.id],),
            name=f"retry-{new_record.id}",
            daemon=True,
        ).start()
        return {"job": new_record.as_dict(), "source_job": job_id}

    @app.get("/api/v1/jobs/{job_id}/events")
    def get_events(job_id: str) -> JSONResponse:
        record = store.get(job_id)
        if record is None or not record.events_path:
            raise HTTPException(status_code=404, detail="事件文件不存在")
        path = Path(record.events_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="事件文件不存在")
        import json

        return JSONResponse(json.loads(path.read_text(encoding="utf-8")))

    @app.get("/api/v1/jobs/{job_id}/video")
    def get_video(job_id: str) -> FileResponse:
        record = store.get(job_id)
        if record is None or not record.video_path:
            raise HTTPException(status_code=404, detail="视频尚未生成")
        path = Path(record.video_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="视频文件不存在")
        return FileResponse(path, media_type="video/mp4", filename=path.name)

    @app.get("/api/v1/jobs/{job_id}/subtitles")
    def get_subtitles(job_id: str) -> FileResponse:
        record = store.get(job_id)
        if record is None or not record.srt_path:
            raise HTTPException(status_code=404, detail="字幕尚未生成")
        path = Path(record.srt_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="字幕文件不存在")
        return FileResponse(path, media_type="text/plain; charset=utf-8", filename=path.name)

    @app.get("/api/v1/stats")
    def stats() -> dict:
        return store.stats()

    @app.get("/gallery", response_class=HTMLResponse)
    def gallery() -> str:
        records = [r for r in store.list(limit=200) if r.status == "completed" and r.video_path]
        cards = []
        for record in records:
            safe_title = html.escape(record.title or "未命名")
            safe_algorithm = html.escape(record.algorithm or "-")
            cards.append(
                f"<article><h3>{safe_title}</h3>"
                f"<p>{safe_algorithm} · {record.duration or 0:.1f}s · verified={record.verified}</p>"
                f"<video controls preload='metadata' src='/api/v1/jobs/{html.escape(record.id)}/video'></video>"
                f"<p><a href='/api/v1/jobs/{html.escape(record.id)}/subtitles'>字幕 SRT</a> · "
                f"<a href='/api/v1/jobs/{html.escape(record.id)}/events'>事件 JSON</a></p></article>"
            )
        html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>AlgoViz 视频库</title>
<style>
body{{font-family:system-ui,-apple-system,'Microsoft YaHei',sans-serif;background:#0b1220;color:#e8eef9;margin:0;padding:32px}}
h1{{font-weight:700}} .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:20px}}
article{{background:#16233d;border:1px solid #2a3b5e;border-radius:14px;padding:16px}}
video{{width:100%;border-radius:10px;background:#000}} a{{color:#fbbf24}}
p{{color:#9aa9c2;font-size:14px}}
</style></head><body><h1>AlgoViz 视频库</h1><div class="grid">{''.join(cards) or '<p>还没有完成的视频</p>'}</div></body></html>"""
        return html

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        workbench_index = static_dir / "workbench" / "index.html"
        if workbench_index.exists():
            return workbench_index.read_text(encoding="utf-8")
        return (static_dir / "index.html").read_text(encoding="utf-8")

    @app.get("/legacy", response_class=HTMLResponse)
    def legacy_index() -> str:
        return (static_dir / "index.html").read_text(encoding="utf-8")

    @app.get("/api")
    def api_info() -> dict:
        return {
            "name": "AlgoViz",
            "version": __version__,
            "gui": "/",
            "legacy_gui": "/legacy",
            "docs": "/docs",
            "gallery": "/gallery",
            "endpoints": [
                "/health",
                "/api/v1/algorithms",
                "/api/v1/settings/ai",
                "/api/v1/ai/test",
                "/api/v1/generate",
                "/api/v1/batch",
                "/api/v1/jobs",
                "/api/v1/jobs/{job_id}",
                "/api/v1/jobs/{job_id}/retry",
                "/api/v1/jobs/{job_id}/video",
                "/api/v1/workbench/projects",
                "/api/v1/workbench/projects/{project_id}/runs",
                "/api/v1/workbench/runs/{run_id}",
                "/api/v1/workbench/runs/{run_id}/classroom",
            ],
        }

    return app
