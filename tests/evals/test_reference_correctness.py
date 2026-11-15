"""Developer-authored oracles, including a shallow implementation that fails hidden cases."""

import pytest

from codeforge.evals.reference import (
    clamp,
    duplicates,
    factorial,
    is_palindrome,
    safe_div,
    shallow_palindrome,
)


def test_palindrome_hidden_cases():
    assert is_palindrome("A man, a plan, a canal: Panama") is True
    assert is_palindrome("") is True
    assert is_palindrome("abc") is False
    assert shallow_palindrome("aba") is True
    assert shallow_palindrome("A man, a plan, a canal: Panama") is False


def test_factorial_boundaries():
    assert factorial(0) == 1
    assert factorial(6) == 720
    with pytest.raises(ValueError):
        factorial(-1)


def test_duplicates_and_clamp_and_division():
    assert duplicates(["a", "b", "a", "c", "b"]) == ["a", "b"]
    assert duplicates([]) == []
    assert clamp(12, 0, 10) == 10
    assert clamp(-4, 0, 10) == 0
    with pytest.raises(ValueError):
        clamp(1, 5, 1)
    assert safe_div(4, 2) == 2
    with pytest.raises(ZeroDivisionError):
        safe_div(1, 0)
