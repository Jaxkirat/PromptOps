"""Gate arithmetic. A high soft score never rescues a failed hard case."""

import pytest

from codeforge.evals.gate import decide_gate


@pytest.mark.parametrize(
    ("hard", "soft", "status"),
    [
        ((20, 20), (20, 20), "GREEN"),
        ((20, 20), (17, 20), "GREEN"),
        ((20, 20), (18, 20), "GREEN"),
        ((20, 20), (16, 20), "RED"),
        ((19, 20), (20, 20), "RED"),
        ((19, 20), (17, 20), "RED"),
    ],
)
def test_threshold_table(hard, soft, status):
    decision = decide_gate(hard[0], hard[1], soft[0], soft[1])
    assert decision.status == status


def test_zero_populations_are_invalid():
    assert decide_gate(0, 0, 10, 10).status == "RED"
    assert decide_gate(10, 10, 0, 0).status == "RED"


def test_infrastructure_failure_is_red():
    decision = decide_gate(20, 20, 20, 20, infrastructure_ok=False, infrastructure_errors=["missing runner"])
    assert decision.status == "RED"
    assert decision.reasons


def test_soft_threshold_does_not_round_up():
    decision = decide_gate(20, 20, 16, 20)
    assert decision.soft_ok is False
    assert decision.status == "RED"
