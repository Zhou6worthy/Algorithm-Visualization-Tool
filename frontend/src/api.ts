import type {
  CaseRunRecord,
  ClassroomEnvelope,
  Project,
  ProjectPayload,
  ProjectSummary,
  RunRecord,
} from "./types";

const BASE = "/api/v1/workbench";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) message = body.detail;
    } catch {
      // Keep the HTTP status when the server did not return JSON.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export const api = {
  listProjects(): Promise<ProjectSummary[]> {
    return request<ProjectSummary[]>("/projects");
  },
  createProject(payload: ProjectPayload): Promise<Project> {
    return request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  getProject(projectId: string): Promise<Project> {
    return request<Project>(`/projects/${encodeURIComponent(projectId)}`);
  },
  updateProject(projectId: string, payload: ProjectPayload): Promise<Project> {
    return request<Project>(`/projects/${encodeURIComponent(projectId)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },
  createRun(projectId: string): Promise<RunRecord> {
    return request<RunRecord>(`/projects/${encodeURIComponent(projectId)}/runs`, {
      method: "POST",
    });
  },
  getRun(runId: string): Promise<RunRecord> {
    return request<RunRecord>(`/runs/${encodeURIComponent(runId)}`);
  },
  getCases(runId: string): Promise<CaseRunRecord[]> {
    return request<CaseRunRecord[]>(`/runs/${encodeURIComponent(runId)}/cases`);
  },
  getClassroom(runId: string): Promise<ClassroomEnvelope> {
    return request<ClassroomEnvelope>(`/runs/${encodeURIComponent(runId)}/classroom`);
  },
  listRuns(projectId: string): Promise<RunRecord[]> {
    return request<RunRecord[]>(`/projects/${encodeURIComponent(projectId)}/runs`);
  },
};

export async function waitForRun(
  runId: string,
  options: { intervalMs?: number; timeoutMs?: number; onUpdate?: (run: RunRecord) => void } = {},
): Promise<RunRecord> {
  const interval = options.intervalMs ?? 500;
  const timeout = options.timeoutMs ?? 180_000;
  const started = Date.now();
  for (;;) {
    const run = await api.getRun(runId);
    options.onUpdate?.(run);
    if (run.status === "completed" || run.status === "failed") return run;
    if (Date.now() - started > timeout) {
      throw new Error("执行超时，请查看服务端日志或稍后重试。");
    }
    await new Promise((resolve) => window.setTimeout(resolve, interval));
  }
}
