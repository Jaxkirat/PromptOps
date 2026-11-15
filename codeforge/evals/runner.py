"""Load, validate and execute the golden dataset."""

from __future__ import annotations

import json
import subprocess
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from codeforge.evals.escalation import escalation_status
from codeforge.evals.execute import execute_case
from codeforge.evals.gate import GateDecision, decide_gate
from codeforge.evals.harness import EvalHarness
from codeforge.evals.schema import GoldenDataset
from codeforge.evals.thresholds import (
    DATASET_VERSION,
    HARD_THRESHOLD_PERCENT,
    SOFT_THRESHOLD_PERCENT,
)

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "golden_set.json"
REPORT_DIR = ROOT / "artifacts"

REQUIRED_PATHS = (
    DATASET_PATH,
    ROOT / "codeforge" / "evals" / "run.py",
    ROOT / "codeforge" / "evals" / "reference.py",
    ROOT / ".github" / "workflows" / "evaluation-gate.yml",
)


@dataclass
class CaseOutcome:
    id: str
    severity: str
    category: str
    status: str
    detail: str


@dataclass
class EvaluationReport:
    dataset_version: str
    generated_at: str
    commit_sha: str | None
    hard_passed: int
    hard_total: int
    soft_passed: int
    soft_total: int
    pending: int
    hard_percent: float
    soft_percent: float
    gate: str
    reasons: list[str]
    cases: list[CaseOutcome] = field(default_factory=list)
    infrastructure_ok: bool = True

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["exit_status"] = 0 if self.gate == "GREEN" else 1
        return payload


def load_dataset(path: Path | None = None) -> GoldenDataset:
    path = path or DATASET_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"golden dataset is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"golden dataset is malformed JSON: {exc}") from exc
    try:
        dataset = GoldenDataset.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"golden dataset failed schema validation: {exc}") from exc
    if dataset.version != DATASET_VERSION:
        raise ValueError(
            f"dataset version {dataset.version} does not match runner {DATASET_VERSION}"
        )
    return dataset


def infrastructure_errors() -> list[str]:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_PATHS if not path.exists()]
    return [f"missing evaluation infrastructure: {', '.join(missing)}"] if missing else []


def _percent(passed: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return (passed * 10000 // total) / 100


def _commit_sha() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def run_dataset(
    *,
    severity: str | None = None,
    category: str | None = None,
    dataset_path: Path | None = None,
) -> EvaluationReport:
    errors = infrastructure_errors()
    try:
        dataset = load_dataset(dataset_path)
    except ValueError as exc:
        decision = decide_gate(0, 0, 0, 0, infrastructure_ok=not errors, infrastructure_errors=errors or [str(exc)])
        return EvaluationReport(
            dataset_version=DATASET_VERSION,
            generated_at=datetime.now(timezone.utc).isoformat(),
            commit_sha=_commit_sha(),
            hard_passed=0,
            hard_total=0,
            soft_passed=0,
            soft_total=0,
            pending=0,
            hard_percent=0,
            soft_percent=0,
            gate="RED",
            reasons=[str(exc), *decision.reasons],
            infrastructure_ok=False,
        )

    selected = []
    for case in dataset.cases:
        if severity and case.severity != severity:
            continue
        if category and case.category != category:
            continue
        selected.append(case)

    outcomes: list[CaseOutcome] = []
    with EvalHarness() as harness:
        for case in selected:
            if case.scoring == "pending":
                detail = case.pending_reason or escalation_status()["detail"]
                outcomes.append(
                    CaseOutcome(case.id, case.severity, case.category, "pending", str(detail))
                )
                continue
            try:
                execute_case(harness, case.model_dump())
            except Exception as exc:  # noqa: BLE001 - a case error is a failed case
                detail = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
                if not detail:
                    detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                outcomes.append(CaseOutcome(case.id, case.severity, case.category, "failed", detail))
            else:
                outcomes.append(CaseOutcome(case.id, case.severity, case.category, "passed", "ok"))

    hard = [item for item in outcomes if item.severity == "hard" and item.status != "pending"]
    soft = [item for item in outcomes if item.severity == "soft" and item.status != "pending"]
    pending = [item for item in outcomes if item.status == "pending"]
    hard_passed = sum(item.status == "passed" for item in hard)
    soft_passed = sum(item.status == "passed" for item in soft)
    filtered = bool(severity or category)
    scored_hard_total = len(hard) if hard or not filtered else 0
    scored_soft_total = len(soft) if soft or not filtered else 0
    if filtered and not hard:
        scored_hard_passed, scored_hard_total = 1, 1
    else:
        scored_hard_passed = hard_passed
        scored_hard_total = len(hard)
    if filtered and not soft:
        scored_soft_passed, scored_soft_total = 1, 1
    else:
        scored_soft_passed = soft_passed
        scored_soft_total = len(soft)
    decision = decide_gate(
        scored_hard_passed,
        scored_hard_total,
        scored_soft_passed,
        scored_soft_total,
        infrastructure_ok=not errors,
        infrastructure_errors=errors,
        pending=len(pending),
    )
    if filtered and not hard:
        decision.hard_passed = 0
        decision.hard_total = 0
        decision.hard_ok = True
    if filtered and not soft:
        decision.soft_passed = 0
        decision.soft_total = 0
        decision.soft_ok = True
    if filtered:
        decision.reasons = [
            reason
            for reason in decision.reasons
            if not (not hard and "hard" in reason.lower())
            and not (not soft and "soft" in reason.lower())
        ]
        decision.status = "GREEN" if decision.hard_ok and decision.soft_ok and not errors else "RED"
        if decision.status == "GREEN":
            decision.reasons = []

    return EvaluationReport(
        dataset_version=dataset.version,
        generated_at=datetime.now(timezone.utc).isoformat(),
        commit_sha=_commit_sha(),
        hard_passed=decision.hard_passed,
        hard_total=decision.hard_total,
        soft_passed=decision.soft_passed,
        soft_total=decision.soft_total,
        pending=len(pending),
        hard_percent=_percent(decision.hard_passed, decision.hard_total),
        soft_percent=_percent(decision.soft_passed, decision.soft_total),
        gate=decision.status,
        reasons=decision.reasons,
        cases=outcomes,
        infrastructure_ok=not errors,
    )


def format_report(report: EvaluationReport) -> str:
    failed = [case for case in report.cases if case.status == "failed"]
    pending = [case for case in report.cases if case.status == "pending"]
    lines = [
        "====================================================",
        "CODEFORGE EVALUATION GATE",
        "====================================================",
        "",
        "Dataset: golden_set.json",
        f"Version: {report.dataset_version}",
        f"Total executed cases: {len(report.cases)}",
        "",
        "HARD EVALUATION",
        f"Passed: {report.hard_passed}/{report.hard_total}",
        f"Score: {report.hard_percent:.2f}%",
        f"Required: {HARD_THRESHOLD_PERCENT:.2f}%",
        f"Status: {'PASS' if report.hard_total and report.hard_passed == report.hard_total else ('N/A' if report.hard_total == 0 else 'FAIL')}",
        "",
        "SOFT EVALUATION",
        f"Passed: {report.soft_passed}/{report.soft_total}",
        f"Score: {report.soft_percent:.2f}%",
        f"Required: {SOFT_THRESHOLD_PERCENT:.2f}%",
        f"Status: {'PASS' if report.soft_total and report.soft_passed * 100 >= report.soft_total * SOFT_THRESHOLD_PERCENT else ('N/A' if report.soft_total == 0 else 'FAIL')}",
        "",
    ]
    if failed:
        lines.append("FAILED CASES:")
        for case in failed:
            lines.append(f"[{case.id}] {case.detail}")
        lines.append("")
    if pending:
        lines.append("PENDING (not scored and not passed):")
        for case in pending:
            lines.append(f"[{case.id}] {case.detail}")
        lines.append("")
    lines.append("----------------------------------------------------")
    lines.append(f"RELEASE GATE: {report.gate}")
    if report.reasons:
        lines.append("Reason: " + " ".join(report.reasons))
    lines.append("----------------------------------------------------")
    return "\n".join(lines)


def write_reports(report: EvaluationReport) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    text = format_report(report)
    (REPORT_DIR / "eval-report.txt").write_text(text + "\n", encoding="utf-8")
    (REPORT_DIR / "eval-report.json").write_text(
        json.dumps(report.to_json(), indent=2),
        encoding="utf-8",
    )
