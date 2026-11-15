"""Hard golden cases drive the real services."""

from codeforge.evals.runner import run_dataset


def test_hard_golden_cases_pass():
    report = run_dataset(severity="hard")
    failed = [case.id for case in report.cases if case.status == "failed"]
    assert failed == []
    assert report.hard_passed == report.hard_total
    assert report.hard_total >= 20
    assert report.gate == "GREEN"
