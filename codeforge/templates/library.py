"""Ten verified Python templates. A validated variation selects the implementation."""

from __future__ import annotations

import re
from dataclasses import dataclass

VERSION = "1"


@dataclass(frozen=True)
class TemplateMatch:
    template_id: str
    name: str
    version: str
    language: str
    variation: str
    code: str
    tests: str


def _unsupported_language(text: str) -> bool:
    return bool(re.search(r"\b(javascript|java|typescript|c\+\+|rust|go)\b", text, re.IGNORECASE))


def _pack(template_id: str, name: str, variation: str, code: str, tests: str) -> TemplateMatch:
    return TemplateMatch(template_id, name, VERSION, "python", variation, code, tests)


def match_template(text: str) -> TemplateMatch | None:
    """Match only a clear request. Ambiguous or unsupported requests return None."""
    if not text or _unsupported_language(text):
        return None
    lowered = text.lower()
    if "binary search" in lowered:
        return _binary("descending" if "descending" in lowered else "ascending")
    if ("maximum" in lowered or "minimum" in lowered) and "sort" not in lowered:
        if "maximum" in lowered and "minimum" in lowered:
            return _minmax("both")
        if "minimum" in lowered:
            return _minmax("minimum")
        return _minmax("maximum")
    if "sort" in lowered and any(word in lowered for word in ("array", "list", "numbers")):
        return _sort("descending" if "descending" in lowered else "ascending")
    if "duplicate" in lowered:
        return _duplicates("sorted" if "sorted" in lowered else "order")
    if "reverse" in lowered and "word" in lowered:
        return _reverse("words")
    if "reverse" in lowered and ("string" in lowered or "text" in lowered):
        return _reverse("characters")
    if "palindrome" in lowered:
        return _palindrome("number" if re.search(r"\bnumber", lowered) else "string")
    if "frequency" in lowered or "character count" in lowered:
        sensitive = "case-sensitive" in lowered or "case sensitive" in lowered
        return _frequency("sensitive" if sensitive else "insensitive")
    if "prime" in lowered:
        return _prime("range" if "range" in lowered else "single")
    if "factorial" in lowered:
        return _factorial("recursive" if "recursive" in lowered else "iterative")
    if "fibonacci" in lowered:
        return _fibonacci("limit" if "limit" in lowered or "up to" in lowered else "count")
    return None


def _sort(variation: str) -> TemplateMatch:
    reverse = "True" if variation == "descending" else "False"
    code = f"def sort_values(values):\n    return sorted(values, reverse={reverse})\n"
    expected = "[3, 2, 1]" if variation == "descending" else "[1, 2, 3]"
    tests = f"""\
from solution import sort_values


def test_order():
    assert sort_values([3, 1, 2]) == {expected}


def test_empty():
    assert sort_values([]) == []
"""
    return _pack("T01", "Array sorting", variation, code, tests)


def _minmax(variation: str) -> TemplateMatch:
    bodies = {
        "maximum": "    return max(values)\n",
        "minimum": "    return min(values)\n",
        "both": "    return (min(values), max(values))\n",
    }
    expectations = {"maximum": "3", "minimum": "1", "both": "(1, 3)"}
    code = "def extreme(values):\n    if not values:\n        raise ValueError('values must not be empty')\n" + bodies[variation]
    tests = f"""\
import pytest

from solution import extreme


def test_value():
    assert extreme([3, 1, 2]) == {expectations[variation]}


def test_empty():
    with pytest.raises(ValueError):
        extreme([])
"""
    return _pack("T02", "Find maximum and minimum", variation, code, tests)


def _duplicates(variation: str) -> TemplateMatch:
    tail = "    return sorted(unique)\n" if variation == "sorted" else "    return unique\n"
    code = "def remove_duplicates(values):\n    unique = []\n    for item in values:\n        if item not in unique:\n            unique.append(item)\n" + tail
    expected = "['a', 'b', 'c']" if variation == "sorted" else "['b', 'a', 'c']"
    tests = f"""\
from solution import remove_duplicates


def test_duplicates():
    assert remove_duplicates(['b', 'a', 'b', 'c', 'a']) == {expected}
"""
    return _pack("T03", "Remove duplicates", variation, code, tests)


def _reverse(variation: str) -> TemplateMatch:
    if variation == "words":
        code = "def reverse_text(value):\n    return ' '.join(str(value).split()[::-1])\n"
        tests = """\
from solution import reverse_text


def test_words():
    assert reverse_text('hello world') == 'world hello'


def test_empty():
    assert reverse_text('') == ''
"""
    else:
        code = "def reverse_text(value):\n    return str(value)[::-1]\n"
        tests = """\
from solution import reverse_text


def test_characters():
    assert reverse_text('ab c') == 'c ba'


def test_empty():
    assert reverse_text('') == ''
"""
    return _pack("T04", "Reverse a string", variation, code, tests)


def _palindrome(variation: str) -> TemplateMatch:
    if variation == "number":
        code = "def is_palindrome(value):\n    text = str(abs(int(value)))\n    return text == text[::-1]\n"
        tests = """\
from solution import is_palindrome


def test_number():
    assert is_palindrome(121) is True
    assert is_palindrome(12) is False
"""
    else:
        code = """\
def is_palindrome(value):
    text = ''.join(ch.lower() for ch in str(value) if ch.isalnum())
    return text == text[::-1]
"""
        tests = """\
from solution import is_palindrome


def test_string():
    assert is_palindrome('A man, a plan, a canal: Panama') is True
    assert is_palindrome('abc') is False
    assert is_palindrome('') is True
"""
    return _pack("T05", "Palindrome checker", variation, code, tests)


def _frequency(variation: str) -> TemplateMatch:
    fold = ".lower()" if variation == "insensitive" else ""
    code = f"""\
def character_frequency(value):
    counts = {{}}
    for character in str(value){fold}:
        counts[character] = counts.get(character, 0) + 1
    return counts
"""
    if variation == "insensitive":
        tests = """\
from solution import character_frequency


def test_insensitive():
    assert character_frequency('aA') == {'a': 2}
"""
    else:
        tests = """\
from solution import character_frequency


def test_sensitive():
    assert character_frequency('aA') == {'a': 1, 'A': 1}
"""
    return _pack("T06", "Character frequency", variation, code, tests)


def _prime(variation: str) -> TemplateMatch:
    code = """\
def is_prime(number):
    if number <= 1:
        return False
    divisor = 2
    while divisor * divisor <= number:
        if number % divisor == 0:
            return False
        divisor += 1
    return True


def primes_in_range(start, end):
    return [number for number in range(start, end + 1) if is_prime(number)]
"""
    if variation == "range":
        tests = """\
from solution import primes_in_range


def test_range():
    assert primes_in_range(0, 10) == [2, 3, 5, 7]
"""
    else:
        tests = """\
from solution import is_prime


def test_edges():
    assert is_prime(0) is False
    assert is_prime(1) is False
    assert is_prime(-5) is False
    assert is_prime(2) is True
    assert is_prime(9) is False
"""
    return _pack("T07", "Prime number checker", variation, code, tests)


def _factorial(variation: str) -> TemplateMatch:
    if variation == "recursive":
        body = """\
def factorial(number):
    if number < 0:
        raise ValueError('factorial is not defined for negative numbers')
    if number in (0, 1):
        return 1
    return number * factorial(number - 1)
"""
    else:
        body = """\
def factorial(number):
    if number < 0:
        raise ValueError('factorial is not defined for negative numbers')
    result = 1
    for value in range(2, number + 1):
        result *= value
    return result
"""
    tests = """\
import pytest

from solution import factorial


def test_zero_and_value():
    assert factorial(0) == 1
    assert factorial(5) == 120


def test_negative():
    with pytest.raises(ValueError):
        factorial(-1)
"""
    return _pack("T08", "Factorial", variation, body, tests)


def _fibonacci(variation: str) -> TemplateMatch:
    code = """\
def fibonacci_count(count):
    if count < 0:
        raise ValueError('count must be non-negative')
    values = []
    current, nxt = 0, 1
    for _ in range(count):
        values.append(current)
        current, nxt = nxt, current + nxt
    return values


def fibonacci_until(limit):
    if limit < 0:
        return []
    values = []
    current, nxt = 0, 1
    while current <= limit:
        values.append(current)
        current, nxt = nxt, current + nxt
    return values
"""
    if variation == "limit":
        tests = """\
from solution import fibonacci_until


def test_limit():
    assert fibonacci_until(0) == [0]
    assert fibonacci_until(5) == [0, 1, 1, 2, 3, 5]
"""
    else:
        tests = """\
import pytest

from solution import fibonacci_count


def test_count():
    assert fibonacci_count(0) == []
    assert fibonacci_count(1) == [0]
    assert fibonacci_count(6) == [0, 1, 1, 2, 3, 5]


def test_negative():
    with pytest.raises(ValueError):
        fibonacci_count(-1)
"""
    return _pack("T09", "Fibonacci sequence", variation, code, tests)


def _binary(variation: str) -> TemplateMatch:
    code = """\
def binary_search(values, target, descending=False):
    low = 0
    high = len(values) - 1
    while low <= high:
        mid = (low + high) // 2
        if values[mid] == target:
            return mid
        go_right = values[mid] > target if descending else values[mid] < target
        if go_right:
            low = mid + 1
        else:
            high = mid - 1
    return -1
"""
    if variation == "descending":
        tests = """\
from solution import binary_search


def test_descending():
    assert binary_search([7, 5, 3, 1], 5, descending=True) == 1
    assert binary_search([7, 5, 3, 1], 4, descending=True) == -1
    assert binary_search([], 1, descending=True) == -1
"""
    else:
        tests = """\
from solution import binary_search


def test_ascending():
    assert binary_search([1, 3, 5, 7], 5) == 2
    assert binary_search([1, 3, 5, 7], 4) == -1
    assert binary_search([], 1) == -1
"""
    return _pack("T10", "Binary search", variation, code, tests)
