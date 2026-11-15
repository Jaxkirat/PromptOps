"""Structured triage. The model classifies. Python decides whether to escalate."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

Sentiment = Literal["positive", "neutral", "negative", "angry"]

_HUMAN = re.compile(
    r"\b(talk to (an? )?(instructor|human|someone|person)|human help|connect me|"
    r"real person|i want a human|instructor)\b",
    re.IGNORECASE,
)
_ANGRY = re.compile(r"\b(unacceptable|furious|angry|ridiculous)\b", re.IGNORECASE)
_COMPLAINT = re.compile(
    r"(not working|isn't working|isnt working|doesn't work|does not work|broken)",
    re.IGNORECASE,
)
_NEGATIVE = re.compile(
    r"(not quite|isn't quite|isnt quite|still not|not what i|did not work|didn't work|not getting)",
    re.IGNORECASE,
)


def _shouted(text: str) -> bool:
    letters = [character for character in text if character.isalpha()]
    if len(letters) < 12:
        return False
    uppercase = sum(character.isupper() for character in letters)
    return uppercase / len(letters) >= 0.7


def _is_angry(text: str) -> bool:
    if _ANGRY.search(text):
        return True
    exclaimed = text.count("!") >= 2
    return exclaimed and (_shouted(text) or bool(_COMPLAINT.search(text)))


class TriageResult(BaseModel):
    task_type: str = "code_generation"
    language: str = "python"
    sentiment: Sentiment = "neutral"
    urgency: int = Field(default=1, ge=1, le=5)
    wants_human: bool = False


def triage_text(text: str) -> TriageResult:
    """Deterministic triage used when a live model call is not requested."""
    raw = text or ""
    wants_human = bool(_HUMAN.search(raw))
    if _is_angry(raw):
        sentiment: Sentiment = "angry"
        urgency = 5
    elif _NEGATIVE.search(text or ""):
        sentiment = "negative"
        urgency = 2
    else:
        sentiment = "neutral"
        urgency = 4 if wants_human else 1
    return TriageResult(
        task_type="code_generation",
        language="python",
        sentiment=sentiment,
        urgency=urgency,
        wants_human=wants_human,
    )
