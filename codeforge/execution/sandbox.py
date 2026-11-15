"""Sandboxed pytest execution.

Docker is the only backend that claims network and filesystem isolation.
``restricted-process`` is an explicit opt-in for safe (policy-allow) code when
Docker is unavailable. It strips the parent environment and enforces an
external timeout, but it does **not** block network or host filesystem access.
Approval-class code is refused on that backend (fail closed).

The Phase 1 ``PytestRunner`` is not called from this module.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from codeforge.config.settings import Settings, get_settings
from codeforge.execution.models import PolicyResult
from codeforge.models.schemas import ExecutionResult

logger = logging.getLogger(__name__)

_PASSED = re.compile(r"(\d+) passed")
_FAILED = re.compile(r"(\d+) failed")
_SKIPPED = re.compile(r"(\d+) skipped")
_ERRORS = re.compile(r"(\d+) error")


def run_sandbox(
    code: str,
    tests: str,
    policy: PolicyResult,
    *,
    approved: bool = False,
    settings: Settings | None = None,
) -> ExecutionResult:
    """Execute pytest under the configured sandbox backend, or fail closed."""
    settings = settings or get_settings()
    backend = settings.sandbox_backend.strip().lower()
    approval_class = policy.decision == "needs_approval" or approved

    if backend == "docker":
        return _run_docker(code, tests, settings, approval_class)
    if backend == "restricted-process":
        if approval_class:
            return _unavailable(
                "restricted-process cannot confine filesystem or network access. "
                "Refusing to execute approval-class code. Start Docker and set "
                "CODEFORGE_SANDBOX_BACKEND=docker."
            )
        return _run_restricted_process(code, tests, settings)
    return _unavailable(
        f"Unknown sandbox backend '{settings.sandbox_backend}'. Execution refused."
    )


def docker_daemon_available() -> bool:
    try:
        completed = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _run_docker(
    code: str, tests: str, settings: Settings, approval_class: bool
) -> ExecutionResult:
    if not docker_daemon_available():
        logger.info("sandbox_unavailable backend=docker reason=daemon")
        return _unavailable(
            "Docker daemon is not available. Execution was not attempted. "
            "Start Docker and build the image with: "
            "docker build -t codeforge-sandbox:latest docker/sandbox"
        )
    workspace = Path(tempfile.mkdtemp(prefix="codeforge_exec_"))
    try:
        (workspace / "solution.py").write_text(code, encoding="utf-8")
        (workspace / "test_solution.py").write_text(tests, encoding="utf-8")
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            f"{settings.sandbox_memory_mb}m",
            "--cpus",
            str(settings.sandbox_cpu_limit),
            "--pids-limit",
            str(settings.sandbox_pids_limit),
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "-v",
            f"{workspace}:/work:rw",
            "-w",
            "/work",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            settings.sandbox_image,
            "python",
            "-m",
            "pytest",
            "-q",
            "test_solution.py",
            "--tb=line",
            "-p",
            "no:cacheprovider",
        ]
        logger.info(
            "sandbox_start backend=docker image=%s timeout=%s approval_class=%s",
            settings.sandbox_image,
            settings.sandbox_timeout_seconds,
            approval_class,
        )
        return _run_command(
            command,
            cwd=None,
            env=None,
            settings=settings,
            backend="docker",
            network_isolated=True,
            filesystem_isolated=True,
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _run_restricted_process(code: str, tests: str, settings: Settings) -> ExecutionResult:
    """Opt-in executor for policy-allow code. Not a network or filesystem sandbox."""
    workspace = Path(tempfile.mkdtemp(prefix="codeforge_exec_"))
    try:
        (workspace / "solution.py").write_text(code, encoding="utf-8")
        (workspace / "test_solution.py").write_text(tests, encoding="utf-8")
        env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "COMSPEC": os.environ.get("COMSPEC", ""),
            "PATHEXT": os.environ.get("PATHEXT", ""),
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        command = [
            sys.executable,
            "-m",
            "pytest",
            "test_solution.py",
            "-q",
            "--tb=line",
            "-p",
            "no:cacheprovider",
        ]
        logger.info(
            "sandbox_start backend=restricted-process timeout=%s network_isolated=false",
            settings.sandbox_timeout_seconds,
        )
        return _run_command(
            command,
            cwd=workspace,
            env=env,
            settings=settings,
            backend="restricted-process",
            network_isolated=False,
            filesystem_isolated=False,
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _run_command(
    command: list[str],
    *,
    cwd: Path | None,
    env: dict[str, str] | None,
    settings: Settings,
    backend: str,
    network_isolated: bool,
    filesystem_isolated: bool,
) -> ExecutionResult:
    import time

    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=settings.sandbox_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        logger.info("sandbox_timeout backend=%s", backend)
        return ExecutionResult(
            status="timeout",
            exit_code=None,
            stdout=_clip(_decode(exc.stdout), settings.sandbox_max_output_bytes),
            stderr=_clip(_decode(exc.stderr), settings.sandbox_max_output_bytes),
            execution_time_seconds=round(elapsed, 3),
            timed_out=True,
            error_message=(
                f"Execution timed out after {settings.sandbox_timeout_seconds}s "
                "and was killed by the sandbox."
            ),
            sandbox_backend=backend,
            network_isolated=network_isolated,
            filesystem_isolated=filesystem_isolated,
            executed=True,
        )
    except OSError as exc:
        return _unavailable(f"Failed to start sandbox process: {exc}")

    elapsed = time.monotonic() - started
    stdout_full = completed.stdout or ""
    stderr_full = completed.stderr or ""
    passed = _num(_PASSED, stdout_full)
    failed = _num(_FAILED, stdout_full) + _num(_ERRORS, stdout_full)
    skipped = _num(_SKIPPED, stdout_full)
    total = passed + failed + skipped
    stdout = _clip(stdout_full, settings.sandbox_max_output_bytes)
    stderr = _clip(stderr_full, settings.sandbox_max_output_bytes)
    if (
        backend == "docker"
        and completed.returncode != 0
        and total == 0
    ):
        detail = (stderr_full or stdout_full or "Docker did not run pytest.").strip()
        logger.info("sandbox_unavailable backend=docker exit=%s", completed.returncode)
        return ExecutionResult(
            status="unavailable",
            exit_code=completed.returncode,
            stdout=_clip(stdout_full, settings.sandbox_max_output_bytes),
            stderr=_clip(stderr_full, settings.sandbox_max_output_bytes),
            execution_time_seconds=round(elapsed, 3),
            error_message=(
                "Docker sandbox did not start pytest. Code was not treated as executed. "
                + detail[:500]
            ),
            sandbox_backend="docker",
            network_isolated=None,
            filesystem_isolated=None,
            executed=False,
        )
    if completed.returncode == 0 and total > 0:
        status, message = "passed", None
    elif completed.returncode == 1:
        status, message = "failed", f"{failed} test(s) failed."
    elif total == 0:
        status, message = "error", "Pytest collected no tests."
    else:
        status, message = "error", f"Pytest exited with code {completed.returncode}."
    logger.info(
        "sandbox_complete backend=%s exit=%s passed=%s failed=%s",
        backend,
        completed.returncode,
        passed,
        failed,
    )
    return ExecutionResult(
        status=status,  # type: ignore[arg-type]
        exit_code=completed.returncode,
        total_tests=total,
        passed_tests=passed,
        failed_tests=failed,
        skipped_tests=skipped,
        stdout=stdout,
        stderr=stderr,
        execution_time_seconds=round(elapsed, 3),
        timed_out=False,
        error_message=message,
        sandbox_backend=backend,
        network_isolated=network_isolated,
        filesystem_isolated=filesystem_isolated,
        executed=True,
    )


def _unavailable(message: str) -> ExecutionResult:
    return ExecutionResult(
        status="unavailable",
        exit_code=None,
        error_message=message,
        sandbox_backend=get_settings().sandbox_backend,
        network_isolated=None,
        filesystem_isolated=None,
        executed=False,
        idempotency_status="not_executed",
    )


def _num(pattern: re.Pattern[str], text: str) -> int:
    match = pattern.search(text)
    return int(match.group(1)) if match else 0


def _decode(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [output truncated at {limit} bytes]"
