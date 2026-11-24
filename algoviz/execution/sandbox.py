"""代码执行沙箱。

M1 只启用 LocalSandbox，且仅用于可信代码/开发测试。
DockerSandbox 在本轮只提供正确的生命周期骨架（M3 加固前不启用）。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..config import get_settings
from ..protocol.execution import ExecutionStatus, TraceLimits
from .python_adapter import PreparedProgram


@dataclass
class SandboxResult:
    status: ExecutionStatus
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    frames_json: str | None = None
    result_json: str | None = None
    duration_ms: float = 0.0
    sandbox: str = "local"
    error: str | None = None
    event_count: int = 0


class SandboxRunner:
    """接口：run(prepared, work_dir, limits) -> SandboxResult。"""

    backend = "local"

    def run(
        self,
        prepared: PreparedProgram,
        work_dir: str | Path,
        limits: TraceLimits | None = None,
    ) -> SandboxResult:
        raise NotImplementedError


class LocalSandbox(SandboxRunner):
    """本地独立进程执行；**不是完整安全沙箱**，只用于可信代码。

    局限：用户代码与 harness/tracer 在同一 Python 解释器，可以调用
    sys.settrace(None)、读取 argv、关闭文件描述符等；因此 M1 只把它用于
    开发者/AC 测试代码，生产必须使用 DockerSandbox。
    """

    backend = "local"

    def __init__(self, timeout_s: float | None = None) -> None:
        self.settings = get_settings()
        self.timeout_s = timeout_s

    def run(
        self,
        prepared: PreparedProgram,
        work_dir: str | Path,
        limits: TraceLimits | None = None,
    ) -> SandboxResult:
        limits = limits or TraceLimits()
        job_dir = Path(work_dir).resolve()
        src_dir = job_dir / "src"
        out_dir = job_dir / "out"
        src_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        user_path = src_dir / prepared.user_filename
        harness_path = src_dir / prepared.harness_filename
        input_path = src_dir / "input.json"
        frames_path = out_dir / "frames.jsonl"
        result_path = out_dir / "result.json"
        user_path.write_bytes(prepared.source.encode("utf-8"))
        harness_path.write_text(prepared.harness_source, encoding="utf-8")
        input_path.write_text(json.dumps(prepared.input_payload, ensure_ascii=False), encoding="utf-8")

        command = [
            sys.executable,
            "-I",
            str(harness_path.resolve()),
            str(user_path.resolve()),
            str(input_path.resolve()),
            str(frames_path.resolve()),
            str(result_path.resolve()),
        ]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        timeout = self.timeout_s or limits.wall_timeout_s
        started = time.time()
        proc = None
        status = ExecutionStatus.OK
        error = None
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=str(src_dir),
                env=env,
            )
            exit_code = proc.returncode
            stdout, stderr = proc.stdout or "", proc.stderr or ""
        except subprocess.TimeoutExpired as exc:
            exit_code = -9
            stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            status = ExecutionStatus.TIMEOUT
            error = f"LocalSandbox 超时：{timeout}s"
        except Exception as exc:  # noqa: BLE001
            exit_code = -1
            stdout, stderr = "", ""
            status = ExecutionStatus.SANDBOX_ERROR
            error = f"{type(exc).__name__}: {exc}"
        duration_ms = round((time.time() - started) * 1000, 3)

        if len(stdout.encode("utf-8")) > limits.max_stdout_bytes:
            status = ExecutionStatus.OUTPUT_LIMIT
            error = "stdout 超过限制"
        if len(stderr.encode("utf-8")) > limits.max_stdout_bytes:
            status = ExecutionStatus.OUTPUT_LIMIT
            error = "stderr 超过限制"

        frames_json = frames_path.read_text(encoding="utf-8", errors="replace") if frames_path.exists() else None
        result_json = result_path.read_text(encoding="utf-8", errors="replace") if result_path.exists() else None
        if result_json is not None:
            try:
                parsed = json.loads(result_json)
                declared = parsed.get("status", "ok")
                if declared in {item.value for item in ExecutionStatus} and status == ExecutionStatus.OK:
                    status = ExecutionStatus(declared)
                error = error or parsed.get("error")
            except json.JSONDecodeError:
                status = ExecutionStatus.TRACE_INCOMPLETE
                error = "result.json 无法解析"
        elif status == ExecutionStatus.OK:
            status = ExecutionStatus.SANDBOX_ERROR
            error = error or "未生成 result.json"

        return SandboxResult(
            status=status,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            frames_json=frames_json,
            result_json=result_json,
            duration_ms=duration_ms,
            sandbox="local",
            error=error,
            event_count=0,
        )


class DockerSandbox(SandboxRunner):
    """Docker 生命周期骨架。

    生命周期：create（不使用 --rm）→ start → wait → docker cp 白名单文件
    → finally docker rm -f。任何异常/超时都会清理容器。
    M1 不启用；M3 才进行生产加固。
    """

    backend = "docker"

    def __init__(
        self,
        image: str = "algoviz-runner-python:3.12",
        docker_bin: str = "docker",
        command_runner: Callable[..., subprocess.CompletedProcess] | None = None,
    ) -> None:
        self.image = image
        self.docker_bin = docker_bin
        self._run_command = command_runner or subprocess.run

    def _docker(self, *args: str, timeout: float = 30.0) -> subprocess.CompletedProcess:
        command = [self.docker_bin, *args]
        return self._run_command(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

    def _create_command(self, name: str, job_dir: Path, limits: TraceLimits) -> list[str]:
        src = job_dir / "src"
        return [
            "create",
            "--name", name,
            "--network", "none",
            "--memory", f"{limits.memory_mb}m",
            "--memory-swap", f"{limits.memory_mb}m",
            "--cpus", "0.5",
            "--pids-limit", "64",
            "--ulimit", f"cpu={int(limits.cpu_time_s)}",
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
            "--tmpfs", "/work/out:rw,noexec,nosuid,size=16m",
            "--user", "65534:65534",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "-v", f"{src}:/work/src:ro",
            self.image,
            "python", "-I", "/work/src/harness.py",
            "/work/src/user_solution.py",
            "/work/src/input.json",
            "/work/out/frames.jsonl",
            "/work/out/result.json",
        ]

    def run(
        self,
        prepared: PreparedProgram,
        work_dir: str | Path,
        limits: TraceLimits | None = None,
    ) -> SandboxResult:
        limits = limits or TraceLimits()
        job_dir = Path(work_dir)
        src_dir = job_dir / "src"
        out_dir = job_dir / "out"
        src_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / prepared.user_filename).write_bytes(prepared.source.encode("utf-8"))
        (src_dir / prepared.harness_filename).write_text(prepared.harness_source, encoding="utf-8")
        (src_dir / "input.json").write_text(json.dumps(prepared.input_payload, ensure_ascii=False), encoding="utf-8")
        name = f"algoviz-{uuid.uuid4().hex[:12]}"
        started = time.time()
        status = ExecutionStatus.OK
        error = None
        frames_json = result_json = None
        try:
            self._docker(*self._create_command(name, job_dir, limits), timeout=60)
            self._docker("start", name, timeout=30)
            wait_proc = None
            try:
                wait_proc = self._docker("wait", name, timeout=limits.wall_timeout_s + 2)
            except subprocess.TimeoutExpired:
                status = ExecutionStatus.TIMEOUT
                error = "Docker wall timeout"
                self._docker("kill", name, timeout=10)
            if wait_proc is not None:
                try:
                    container_exit = int((wait_proc.stdout or "").strip() or "-1")
                except ValueError:
                    container_exit = -1
                if container_exit == 137:
                    status = ExecutionStatus.SANDBOX_ERROR
                    error = "Docker container OOM (exit 137)"
                elif container_exit not in {0, -1} and status == ExecutionStatus.OK:
                    status = ExecutionStatus.SANDBOX_ERROR
                    error = f"Docker container exited with {container_exit}"
            # 只有 wait 结束后才 cp；容器未使用 --rm，仍然存在
            for filename, target in (("frames.jsonl", "frames"), ("result.json", "result")):
                try:
                    proc = self._docker("cp", f"{name}:/work/out/{filename}", str(job_dir / filename), timeout=30)
                    if proc.returncode != 0:
                        raise RuntimeError(f"docker cp {filename} 失败：{proc.stderr[-300:]}")
                    max_bytes = limits.max_stdout_bytes * 4
                    path = job_dir / filename
                    if path.stat().st_size > max_bytes:
                        raise RuntimeError(f"{filename} 超过白名单大小限制")
                except Exception as exc:  # noqa: BLE001
                    if status == ExecutionStatus.OK:
                        status = ExecutionStatus.TRACE_INCOMPLETE
                    error = error or str(exc)
            frames_path = job_dir / "frames.jsonl"
            result_path = job_dir / "result.json"
            frames_json = frames_path.read_text(encoding="utf-8") if frames_path.exists() else None
            result_json = result_path.read_text(encoding="utf-8") if result_path.exists() else None
            if result_json is None and status == ExecutionStatus.OK:
                status = ExecutionStatus.TRACE_INCOMPLETE
                error = error or "缺少 result.json"
        except Exception as exc:  # noqa: BLE001
            status = ExecutionStatus.SANDBOX_ERROR
            error = f"{type(exc).__name__}: {exc}"
        finally:
            # 无论成功、超时、copy 失败都清理；不使用 --rm
            try:
                self._docker("rm", "-f", name, timeout=20)
            except Exception:  # noqa: BLE001
                pass
        return SandboxResult(
            status=status,
            frames_json=frames_json,
            result_json=result_json,
            duration_ms=round((time.time() - started) * 1000, 3),
            sandbox="docker",
            error=error,
        )
