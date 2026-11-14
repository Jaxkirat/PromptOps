"""Development-stage execution runner for generated code and tests.

The runner writes the generated implementation and tests to a unique temporary
directory and executes pytest in a **separate subprocess** with a configurable
timeout. Generated code never runs inside the main application process.

NOTE (Phase 1): subprocess isolation + temp directory + timeout are baseline
development safeguards only. This is NOT a production-secure sandbox. The R2
policy gate and a hardened sandbox will be inserted in front of this interface
in a later phase, which is why all execution goes through the single
``PytestRunner.run`` entry point.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from codeforge.config.settings import Settings, get_settings
from codeforge.models.schemas import ExecutionResult

logger = logging.getLogger(__name__)

SOLUTION_FILENAME = "solution.py"
TEST_FILENAME = "test_solution.py"

_RESULT_PATTERNS = {
    "passed": re.compile(r"(\d+) passed"),
    "failed": re.compile(r"(\d+) failed"),
    "skipped": re.compile(r"(\d+) skipped"),
    "errors": re.compile(r"(\d+) error"),
}


def _count(pattern_key: str, output: str) -> int:
    match = _RESULT_PATTERNS[pattern_key].search(output)
    return int(match.group(1)) if match else 0


class PytestRunner:
    """Runs generated implementation + pytest tests in an isolated subprocess."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def run(self, implementation_code: str, test_code: str) -> ExecutionResult:
        """Write code and tests to a temp directory, run pytest, and report results.

        The returned :class:`ExecutionResult` reflects the **actual** pytest
        process exit code and parsed test counts — never an LLM claim.
        """
        timeout = self._settings.execution_timeout_seconds
        max_len = self._settings.max_test_output_length
        workdir = Path(tempfile.mkdtemp(prefix="codeforge_run_"))
        logger.info("Executing generated tests in %s (timeout=%ss)", workdir, timeout)

        try:
            (workdir / SOLUTION_FILENAME).write_text(implementation_code, encoding="utf-8")
            (workdir / TEST_FILENAME).write_text(test_code, encoding="utf-8")

            command = [
                sys.executable,
                "-m",
                "pytest",
                TEST_FILENAME,
                "-v",
                "--tb=short",
                "-p",
                "no:cacheprovider",
            ]

            start = time.monotonic()
            try:
                process = subprocess.run(
                    command,
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                elapsed = time.monotonic() - start
                return ExecutionResult(
                    status="timeout",
                    exit_code=None,
                    stdout=_truncate(_decode(exc.stdout), max_len),
                    stderr=_truncate(_decode(exc.stderr), max_len),
                    execution_time_seconds=round(elapsed, 3),
                    timed_out=True,
                    error_message=f"Test execution exceeded the {timeout}s timeout.",
                )
            except OSError as exc:
                elapsed = time.monotonic() - start
                return ExecutionResult(
                    status="error",
                    exit_code=None,
                    execution_time_seconds=round(elapsed, 3),
                    error_message=f"Failed to start the pytest subprocess: {exc}",
                )

            elapsed = time.monotonic() - start
            stdout = process.stdout or ""
            stderr = process.stderr or ""

            passed = _count("passed", stdout)
            failed = _count("failed", stdout) + _count("errors", stdout)
            skipped = _count("skipped", stdout)
            total = passed + failed + skipped

            if process.returncode == 0 and total > 0:
                status, error_message = "passed", None
            elif process.returncode == 1:
                status, error_message = "failed", f"{failed} test(s) failed."
            elif process.returncode == 5 or total == 0:
                status = "error"
                error_message = "Pytest collected no tests (possible syntax or import error)."
            else:
                status = "error"
                error_message = f"Pytest exited abnormally with code {process.returncode}."

            return ExecutionResult(
                status=status,
                exit_code=process.returncode,
                total_tests=total,
                passed_tests=passed,
                failed_tests=failed,
                skipped_tests=skipped,
                stdout=_truncate(stdout, max_len),
                stderr=_truncate(stderr, max_len),
                execution_time_seconds=round(elapsed, 3),
                timed_out=False,
                error_message=error_message,
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


def _decode(data: object) -> str:
    """Normalise subprocess output that may be bytes, str, or None."""
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def _truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length] + f"\n... [output truncated at {max_length} characters]"
