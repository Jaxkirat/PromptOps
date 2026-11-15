"""R5 template, fallback, and chaos tests. No live provider calls."""

import random

from codeforge.resilience.circuit import breakers
from codeforge.resilience.errors import AllProvidersFailed, FatalProviderError, TransientProviderError
from codeforge.resilience.fallback import ResilientChatModel
from codeforge.resilience.retry import set_retry_sleeper
from codeforge.templates.library import match_template
from codeforge.templates.runner import run_template


def setup_function():
    breakers.reset()
    breakers.threshold = 5
    breakers.cooldown = 30
    set_retry_sleeper(lambda _delay: None)
    from codeforge.resilience.chaos import set_chaos_decider

    set_chaos_decider(None)


def test_all_ten_templates_match_supported_variations():
    samples = {
        "T01": "Sort the list in descending order",
        "T02": "Find the maximum and minimum",
        "T03": "Remove duplicates and keep sorted output",
        "T04": "Reverse the string",
        "T05": "Check a palindrome string",
        "T06": "Character frequency case-sensitive",
        "T07": "Check if a number is prime",
        "T08": "Recursive factorial",
        "T09": "Fibonacci up to a limit",
        "T10": "Binary search a descending list",
    }
    found = {match_template(text).template_id for text in samples.values()}
    assert found == set(samples)
    assert match_template("Sort this javascript list") is None
    assert match_template("Help me design a database") is None


def test_template_behavior():
    assert _call(match_template("Sort the numbers ascending"), "sort_values", [3, 1, 2]) == [1, 2, 3]
    assert _call(match_template("Sort the list descending"), "sort_values", [3, 1, 2]) == [3, 2, 1]
    assert _call(match_template("Remove duplicates preserve order"), "remove_duplicates", ["b", "a", "b"]) == ["b", "a"]
    assert _call(match_template("Reverse the string text"), "reverse_text", "ab c") == "c ba"
    assert _call(match_template("Reverse the word order"), "reverse_text", "hello world") == "world hello"
    assert _call(match_template("Is this string a palindrome"), "is_palindrome", "A man, a plan, a canal: Panama") is True
    assert _call(match_template("Is this number a palindrome"), "is_palindrome", 121) is True
    assert _call(match_template("character frequency case-sensitive"), "character_frequency", "aA") == {"a": 1, "A": 1}
    assert _call(match_template("character frequency"), "character_frequency", "aA") == {"a": 2}
    assert _call(match_template("check a prime number"), "is_prime", 0) is False
    assert _call(match_template("check a prime number"), "is_prime", 1) is False
    assert _call(match_template("check a prime number"), "is_prime", -3) is False
    assert _call(match_template("check a prime number"), "is_prime", 2) is True
    assert _call(match_template("iterative factorial"), "factorial", 0) == 1
    try:
        _call(match_template("iterative factorial"), "factorial", -1)
        raise AssertionError("negative factorial was accepted")
    except ValueError:
        pass
    assert _call(match_template("fibonacci first n"), "fibonacci_count", 1) == [0]
    assert _call(match_template("binary search ascending"), "binary_search", [1, 3, 5], 4) == -1


def test_template_really_runs_in_the_sandbox():
    match = match_template("Sort the list ascending")
    state = run_template("Sort the list ascending", match)
    assert state["report"].status == "success"
    assert state["report"].tests_passed is True
    assert state["report"].execution.executed is True
    assert state["report"].execution.policy_decision == "allow"


def test_template_hit_uses_the_sandbox(monkeypatch):
    calls = {}

    def fake_sandbox(code, tests, policy, **_kwargs):
        calls["code"] = code
        from codeforge.models.schemas import ExecutionResult

        return ExecutionResult(status="passed", exit_code=0, total_tests=1, passed_tests=1, executed=True)

    monkeypatch.setattr("codeforge.templates.runner.run_sandbox", fake_sandbox)
    match = match_template("Sort the list ascending")
    state = run_template("Sort the list ascending", match)
    assert calls["code"].startswith("def sort_values")
    assert state["report"].status == "success"
    assert state["resilience"]["template_id"] == "T01"
    assert state["resilience"]["generation_source"] == "template"


def _call(match, name, *args):
    namespace: dict = {}
    exec(match.code, namespace)
    return namespace[name](*args)


class _Script:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)

    def invoke(self, *_args, **_kwargs):
        item = self.outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def with_structured_output(self, _schema, **_kwargs):
        return self


def _settings():
    from codeforge.config.settings import get_settings

    return get_settings()


def test_fallback_and_no_retry_on_auth():
    settings = _settings()
    fail = TransientProviderError("429")
    model = ResilientChatModel(
        [("groq", "g", _Script([fail, "groq-ok"])), ("openai", "gpt-4o-mini", _Script(["unused"]))],
        settings,
    )
    assert model.invoke("hi") == "groq-ok"
    fatal = ResilientChatModel(
        [("groq", "g", _Script([FatalProviderError("invalid api key")])), ("openai", "gpt-4o-mini", _Script(["openai-ok"]))],
        settings,
    )
    assert fatal.invoke("hi") == "openai-ok"
    down = ResilientChatModel(
        [("groq", "g", _Script([fail, fail, fail])), ("openai", "gpt-4o-mini", _Script([fail, fail, fail]))],
        settings,
    )
    try:
        down.invoke("hi")
        raise AssertionError("all providers were treated as successful")
    except AllProvidersFailed:
        pass


def test_circuit_opens_and_recovers():
    settings = _settings()
    fail = TransientProviderError("503")
    groq = _Script([fail, fail, fail, fail, fail, fail, "recovered"])
    model = ResilientChatModel([("groq", "g", groq), ("openai", "m", _Script(["fallback"] * 4))], settings)
    object.__setattr__(settings, "llm_circuit_breaker_threshold", 5) if False else None
    breakers.threshold = 2
    breakers.cooldown = 30
    assert model.invoke("a") == "fallback"
    assert model.invoke("b") == "fallback"
    assert breakers.state_of("groq") == "open"
    assert model.invoke("c") == "fallback"
    breakers._states["groq"]["opened_at"] -= 31
    assert model.invoke("d") == "recovered"
    assert breakers.state_of("groq") == "closed"


def test_chaos_is_off_by_default_and_rate_is_controlled(monkeypatch):
    from codeforge.config.settings import get_settings
    from codeforge.resilience.chaos import chaos_should_fail, set_chaos_rng

    get_settings.cache_clear()
    assert get_settings().chaos_enabled is False
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CODEFORGE_CHAOS_ENABLED", "true")
    get_settings.cache_clear()
    assert get_settings().chaos_enabled is False
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CODEFORGE_CHAOS_FAILURE_RATE", "0.6")
    get_settings.cache_clear()
    set_chaos_rng(random.Random(1))
    failures = sum(chaos_should_fail() for _ in range(1000))
    assert 500 < failures < 700


def test_workload_report_is_honest():
    from codeforge.evals.resilience_workload import run_workload

    report = run_workload(_settings())
    assert report["total"] == 20
    assert report["template_hits"] >= 10
    assert report["all_failed"] >= 1
    assert report["answered"] == report["template_hits"] + report["llm_answers"]
    assert report["answered"] < 20 or report["all_failed"] == 0
