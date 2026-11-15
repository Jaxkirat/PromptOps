"""One missed hard case must turn the release gate red."""

from codeforge.evals.gate import decide_gate
from codeforge.evals.runner import load_dataset
from codeforge.evals.thresholds import HARD_THRESHOLD_PERCENT, SOFT_THRESHOLD_PERCENT


def test_workspace_builds():
    from codeforge.ui.app import build_interface

    assert build_interface() is not None


def test_thresholds_are_unchanged():
    assert HARD_THRESHOLD_PERCENT == 100
    assert SOFT_THRESHOLD_PERCENT == 85


def test_one_r7_hard_failure_makes_the_gate_red():
    dataset = load_dataset()
    hard = [case for case in dataset.cases if case.severity == "hard" and case.scoring == "scored"]
    soft = [case for case in dataset.cases if case.severity == "soft" and case.scoring == "scored"]
    assert any(case.id.startswith("H-R7-") for case in hard)
    decision = decide_gate(
        len(hard) - 1,
        len(hard),
        len(soft),
        len(soft),
        infrastructure_ok=True,
        infrastructure_errors=[],
        pending=1,
    )
    assert decision.status == "RED"
    assert decision.hard_ok is False
    assert decision.soft_ok is True
