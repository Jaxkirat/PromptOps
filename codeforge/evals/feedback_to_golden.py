"""Turn a stored thumbs-down into a pending golden case.

    python -m codeforge.evals.feedback_to_golden --feedback-id ID --expected expected.json --input input.json --description "..."

A developer must supply the expected behavior. The model's previous output is
never copied in as the oracle. Pending cases are not part of the release gate
until a person promotes them into golden_set.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from codeforge.database.database import session_scope
from codeforge.database.models import RunFeedback
from codeforge.evals.schema import GoldenCase

ROOT = Path(__file__).resolve().parents[2]
PENDING_DIR = ROOT / "golden_cases" / "pending"


def feedback_to_case(
    feedback_id: str,
    *,
    expected: dict,
    case_input: dict,
    description: str,
    category: str = "feedback",
    severity: str = "soft",
) -> GoldenCase:
    if not expected:
        raise ValueError("A developer-authored expected result is required")
    with session_scope() as db:
        row = db.get(RunFeedback, feedback_id)
        if row is None:
            raise ValueError("Feedback record was not found")
        if row.vote != "down":
            raise ValueError("Only thumbs-down feedback can become a golden candidate")
        case = GoldenCase(
            id=f"F-{row.id[:8].upper()}",
            category=category,
            severity=severity,  # type: ignore[arg-type]
            description=description,
            input={
                "feedback_id": row.id,
                "run_id": row.run_id,
                "sanitised_request": row.sanitised_request,
                **case_input,
            },
            expected=expected,
            tags=["feedback", "candidate"],
            enabled=True,
            mandatory=False,
            scoring="scored",
        )
    return case


def write_pending(case: GoldenCase, directory: Path | None = None) -> Path:
    target = directory or PENDING_DIR
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{case.id}.json"
    path.write_text(case.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_pending(path: Path) -> GoldenCase:
    return GoldenCase.model_validate(json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a pending golden case from thumbs-down feedback")
    parser.add_argument("--feedback-id", required=True)
    parser.add_argument("--expected", required=True, help="JSON file with the developer-authored oracle")
    parser.add_argument("--input", dest="case_input", required=True, help="JSON file with the case input")
    parser.add_argument("--description", required=True)
    parser.add_argument("--category", default="feedback")
    parser.add_argument("--severity", choices=("hard", "soft"), default="soft")
    args = parser.parse_args(argv)
    expected = json.loads(Path(args.expected).read_text(encoding="utf-8"))
    case_input = json.loads(Path(args.case_input).read_text(encoding="utf-8"))
    case = feedback_to_case(
        args.feedback_id,
        expected=expected,
        case_input=case_input,
        description=args.description,
        category=args.category,
        severity=args.severity,
    )
    path = write_pending(case)
    print(f"Wrote pending golden case {case.id} to {path}")
    print("Review it, then promote it by adding the case to golden_set.json and an executor.")
    print("Pending cases are not part of the release gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
