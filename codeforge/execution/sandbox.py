"""Pytest execution for policy-allow code.

The runner strips the parent environment and enforces an external timeout.
It does not block network or host filesystem access, so approval-class code
is refused. Docker is not used.
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
    approval_class = policy.decision == "needs_approval" or approved
    if approval_class:
        result = _unavailable(
            "File and network operations are not executed. "
            "This runner only runs policy-allow code."
        )
    else:
        result = _run_restricted_process(code, tests, settings)
    # Always persist the gate outcome — callers (especially templates) previously
    # left this None on successful allow runs, so the UI showed "not evaluated".
    result.policy_decision = policy.decision
    result.policy_reasons = list(policy.reasons or [])
    return result


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
