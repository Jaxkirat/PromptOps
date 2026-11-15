"""Local pytest runner tests.

Allow-class code runs in a temp directory with a timeout. It must not be
described as network isolation. File and network code is refused.
"""

import os

from codeforge.config.settings import Settings, get_settings
from codeforge.execution.models import PolicyResult
from codeforge.execution.sandbox import run_sandbox

ALLOW = PolicyResult(decision="allow", reasons=["safe"])
APPROVAL = PolicyResult(decision="needs_approval", reasons=["open"])

PASSING = "def add(a, b):\n    return a + b\n"
PASSING_TESTS = "from solution import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
FAILING_TESTS = "from solution import add\n\ndef test_add():\n    assert add(1, 2) == 9\n"


def _settings(**overrides) -> Settings:
    current = get_settings()
    data = {field: getattr(current, field) for field in current.__dataclass_fields__}
    data.update(overrides)
    return Settings(**data)


def test_valid_pytest_passes():
    result = run_sandbox(PASSING, PASSING_TESTS, ALLOW, settings=_settings())
    assert result.status == "passed"
    assert result.exit_code == 0
    assert result.passed_tests == 1
    assert result.executed is True
    assert result.network_isolated is False
    assert result.sandbox_backend == "restricted-process"
    assert result.policy_decision == "allow"
    assert result.policy_reasons == ["safe"]


def test_failing_pytest_is_not_success():
    result = run_sandbox(PASSING, FAILING_TESTS, ALLOW, settings=_settings())
    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.executed is True


def test_timeout_kills_infinite_loop():
    code = "def loop():\n    while True:\n        pass\n"
    tests = "from solution import loop\n\ndef test_loop():\n    loop()\n"
    result = run_sandbox(code, tests, ALLOW, settings=_settings(sandbox_timeout_seconds=2))
    assert result.status == "timeout"
    assert result.timed_out is True
    assert result.executed is True


def test_parent_secrets_are_not_passed(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "super-secret-value")
    code = "import os\n\ndef secret():\n    return os.environ.get('LLM_API_KEY')\n"
    tests = (
        "from solution import secret\n\n"
        "def test_secret():\n"
        "    assert secret() is None\n"
    )
    # import os is needs_approval, so this must NOT run on restricted-process.
    policy = PolicyResult(decision="needs_approval", reasons=["import os"])
    result = run_sandbox(code, tests, policy, approved=True, settings=_settings())
    assert result.status == "unavailable"
    assert result.executed is False


def test_allow_code_does_not_see_parent_secret(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "super-secret-value")
    code = "def secret():\n    return __import__('os').environ.get('LLM_API_KEY')\n"
    # __import__ is denied by policy; this test only checks the backend when
    # the caller has already classified the code as allow. The backend still
    # strips the parent environment.
    tests = "from solution import secret\n\ndef test_secret():\n    assert secret() is None\n"
    result = run_sandbox(code, tests, ALLOW, settings=_settings())
    assert result.status == "passed"
    assert result.exit_code == 0


def test_output_is_truncated():
    code = "def blob():\n    return 'x' * 5000\n"
    tests = "from solution import blob\n\ndef test_blob():\n    print(blob())\n    assert True\n"
    result = run_sandbox(code, tests, ALLOW, settings=_settings(sandbox_max_output_bytes=80))
    assert result.status == "passed"
    assert "truncated" in result.stdout


def test_approval_class_is_refused():
    result = run_sandbox("def read():\n    return open('a').read()\n", "def test_x():\n    assert True\n", APPROVAL, approved=True)
    assert result.status == "unavailable"
    assert result.executed is False
    assert result.policy_decision == "needs_approval"
    assert result.policy_reasons == ["open"]


def test_backend_name_does_not_select_another_runner():
    result = run_sandbox(PASSING, PASSING_TESTS, ALLOW, settings=_settings(sandbox_backend="nope"))
    assert result.status == "passed"
    assert result.executed is True
    assert result.network_isolated is False
