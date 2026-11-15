"""Soft golden cases, with R3 escalation left pending rather than passed."""

from codeforge.evals.runner import run_dataset


def test_soft_golden_cases_meet_the_threshold():
    report = run_dataset(severity="soft")
    failed = [case.id for case in report.cases if case.status == "failed"]
    pending = [case.id for case in report.cases if case.status == "pending"]
    assert failed == []
    assert report.soft_passed == report.soft_total
    assert report.soft_total >= 20
    assert not any(case_id.startswith("S-ESC-") for case_id in pending)
    assert report.gate == "GREEN"


def test_full_gate_is_green():
    report = run_dataset()
    assert report.gate == "GREEN"
    assert report.hard_passed == report.hard_total
    assert report.soft_passed * 100 >= report.soft_total * 85
