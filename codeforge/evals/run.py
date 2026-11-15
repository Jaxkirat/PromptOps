"""Command line for the CodeForge evaluation gate.

    python -m codeforge.evals.run
    python -m codeforge.evals.run --severity hard
    python -m codeforge.evals.run --severity soft
    python -m codeforge.evals.run --category identity
    python -m codeforge.evals.run --json
"""

from __future__ import annotations

import argparse
import json
import sys

from codeforge.evals.runner import format_report, run_dataset, write_reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the CodeForge golden evaluation gate")
    parser.add_argument("--severity", choices=("hard", "soft"))
    parser.add_argument("--category")
    parser.add_argument("--json", action="store_true", help="Print the JSON report as well")
    args = parser.parse_args(argv)
    report = run_dataset(severity=args.severity, category=args.category)
    write_reports(report)
    print(format_report(report))
    if args.json:
        print(json.dumps(report.to_json(), indent=2))
    return 0 if report.gate == "GREEN" else 1


if __name__ == "__main__":
    sys.exit(main())
