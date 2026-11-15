"""Developer-authored reference implementations.

These oracles are maintained by the team. Generated tests are not the source of truth.
"""

from __future__ import annotations


def is_palindrome(text: str) -> bool:
    cleaned = "".join(character.lower() for character in text if character.isalnum())
    return cleaned == cleaned[::-1]


def shallow_palindrome(text: str) -> bool:
    """Passes a trivial example and fails the hidden punctuation case."""
    return text == text[::-1]


def factorial(n: int) -> int:
    if n < 0:
        raise ValueError("n must be non-negative")
    result = 1
    for value in range(2, n + 1):
        result *= value
    return result


def duplicates(values: list) -> list:
    seen: set = set()
    repeated: list = []
    for value in values:
        if value in seen and value not in repeated:
            repeated.append(value)
        seen.add(value)
    return repeated


def clamp(value: int, low: int, high: int) -> int:
    if low > high:
        raise ValueError("low must be <= high")
    return max(low, min(high, value))


def safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        raise ZeroDivisionError("division by zero")
    return numerator / denominator
