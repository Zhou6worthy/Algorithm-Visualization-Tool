"""FastAPI routes for the M4 workbench."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from .models import ClassroomEnvelope, ProjectPayload
from .service import WorkbenchRunService
from .store import WorkbenchStore


def create_workbench_router(store: WorkbenchStore, service: WorkbenchRunService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workbench", tags=["workbench"])

    @router.get("/projects")
    def list_projects() -> list[dict]:
        return [item.model_dump(mode="json") for item in store.list_projects()]

    @router.post("/projects", status_code=status.HTTP_201_CREATED)
    def create_project(payload: ProjectPayload) -> dict:
        return store.create_project(payload)

    @router.get("/projects/{project_id}")
    def get_project(project_id: str) -> dict:
        project = store.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        return project

    @router.put("/projects/{project_id}")
    def update_project(project_id: str, payload: ProjectPayload) -> dict:
        try:
            return store.update_project(project_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="项目不存在") from exc

    @router.get("/projects/{project_id}/runs")
    def list_project_runs(project_id: str, limit: int = Query(default=30, ge=1, le=200)) -> list[dict]:
        if store.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        return [item.model_dump(mode="json") for item in store.list_runs(project_id, limit=limit)]

    @router.post("/projects/{project_id}/runs", status_code=status.HTTP_202_ACCEPTED)
    def create_run(project_id: str) -> dict:
        try:
            run = store.create_run(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="项目不存在") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        service.submit(run.run_id)
        current = store.get_run(run.run_id)
        return (current or run).model_dump(mode="json")

    @router.get("/runs")
    def list_runs(
        project_id: str | None = None,
        limit: int = Query(default=30, ge=1, le=200),
    ) -> list[dict]:
        return [item.model_dump(mode="json") for item in store.list_runs(project_id, limit=limit)]

    @router.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="执行任务不存在")
        return run.model_dump(mode="json")

    @router.get("/runs/{run_id}/cases")
    def get_run_cases(run_id: str) -> list[dict]:
        if store.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="执行任务不存在")
        return [item.model_dump(mode="json") for item in store.get_case_runs(run_id)]

    @router.get("/runs/{run_id}/cases/{case_id}")
    def get_case_run(run_id: str, case_id: str) -> dict:
        if store.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="执行任务不存在")
        case = store.get_case_run(run_id, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="测试用例结果不存在")
        return case

    @router.get("/runs/{run_id}/classroom", response_model=ClassroomEnvelope)
    def get_classroom(run_id: str) -> ClassroomEnvelope:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="执行任务不存在")
        if run.status in {"queued", "running"}:
            raise HTTPException(status_code=409, detail="执行尚未完成，请稍后轮询")
        if run.status == "failed":
            raise HTTPException(status_code=409, detail=run.error or "执行失败")
        classroom = store.get_classroom(run_id)
        if classroom is None:
            raise HTTPException(status_code=404, detail="课堂数据不存在")
        return ClassroomEnvelope(
            run=run,
            cases=store.get_case_runs(run_id),
            classroom=classroom,
        )

    return router
