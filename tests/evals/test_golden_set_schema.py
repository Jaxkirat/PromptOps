"""Schema checks for golden_set.json."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from codeforge.evals.schema import GoldenDataset
from codeforge.evals.thresholds import DATASET_VERSION


ROOT = Path(__file__).resolve().parents[2]


def test_dataset_file_matches_schema():
    raw = json.loads((ROOT / "golden_set.json").read_text(encoding="utf-8"))
    dataset = GoldenDataset.model_validate(raw)
    assert dataset.version == DATASET_VERSION
    hard = [case for case in dataset.cases if case.severity == "hard"]
    soft = [case for case in dataset.cases if case.severity == "soft" and case.scoring == "scored"]
    pending = [case for case in dataset.cases if case.scoring == "pending"]
    assert len(hard) >= 20
    assert len(soft) >= 20
    assert pending == []
    assert any(case.id.startswith("H-R3-") for case in dataset.cases)
    assert len({case.id for case in dataset.cases}) == len(dataset.cases)


def test_duplicate_ids_are_rejected():
    payload = {
        "version": "r6.1",
        "description": "duplicate check for the golden schema",
        "cases": [
            _case("H-1"),
            _case("H-1"),
            _case("S-1", severity="soft"),
        ],
    }
    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)


def test_missing_expected_is_rejected():
    case = _case("H-1")
    case["expected"] = {}
    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(
            {"version": "r6.1", "description": "missing expected outcomes", "cases": [case, _case("S-1", "soft")]}
        )


def test_invalid_severity_is_rejected():
    case = _case("H-1")
    case["severity"] = "medium"
    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(
            {"version": "r6.1", "description": "bad severity is rejected", "cases": [case, _case("S-1", "soft")]}
        )


def test_disabled_mandatory_case_is_rejected():
    hard = _case("H-1")
    hard["enabled"] = False
    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(
            {
                "version": "r6.1",
                "description": "disabled mandatory case",
                "cases": [hard, _case("S-1", "soft")],
            }
        )


def test_zero_hard_cases_is_rejected():
    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(
            {"version": "r6.1", "description": "no hard cases here", "cases": [_case("S-1", "soft")]}
        )


def _case(case_id: str, severity: str = "hard") -> dict:
    return {
        "id": case_id,
        "category": "identity" if severity == "hard" else "routing",
        "severity": severity,
        "description": "A schema fixture case",
        "input": {"value": 1},
        "expected": {"ok": True},
        "enabled": True,
        "mandatory": True,
        "scoring": "scored",
    }
