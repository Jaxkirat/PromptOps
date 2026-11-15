"""AST policy engine tests. Evaluation must never execute the submitted code."""

from pathlib import Path

from codeforge.execution.policy import evaluate_code_policy

SAFE_SAMPLES = {
    "arithmetic": "def add(a, b):\n    return a + b\n",
    "comprehension": "def squares(values):\n    return [v * v for v in values]\n",
    "strings": "def shout(text):\n    return text.strip().upper()\n",
    "sorting": "def ordered(values):\n    return sorted(values)\n",
    "dict": "def tally(items):\n    return {item: items.count(item) for item in items}\n",
    "class": "class Box:\n    def __init__(self, value):\n        self.value = value\n",
    "functools": "from functools import reduce\n\ndef total(values):\n    return reduce(lambda a, b: a + b, values, 0)\n",
    "typing": "from typing import Union\n\ndef ident(value: Union[int, str]):\n    return value\n",
    "loop": "while True:\n    pass\n",
}

APPROVAL_SAMPLES = {
    "open": "def read(path):\n    return open(path).read()\n",
    "pathlib_read": "from pathlib import Path\n\ndef read(path):\n    return Path(path).read_text()\n",
    "pathlib_write": "from pathlib import Path\n\ndef write(path):\n    Path(path).write_text('x')\n",
    "socket": "import socket\n\ndef connect():\n    return socket.socket()\n",
    "requests": "import requests\n\ndef fetch():\n    return requests.get('https://example.com')\n",
    "urllib": "from urllib.request import urlopen\n\ndef fetch():\n    return urlopen('https://example.com')\n",
}

DENY_SAMPLES = {
    "os_system": "import os\n\ndef run():\n    os.system('echo hi')\n",
    "subprocess": "import subprocess\n\ndef run():\n    subprocess.run(['echo', 'hi'])\n",
    "rmtree": "import shutil\n\ndef wipe():\n    shutil.rmtree('/tmp/somewhere')\n",
    "remove": "import os\n\ndef wipe(path):\n    os.remove(path)\n",
    "eval": "def run(text):\n    return eval(text)\n",
    "exec": "def run(text):\n    exec(text)\n",
    "importlib": "import importlib\n\ndef load(name):\n    return importlib.import_module(name)\n",
    "dunder": "def escape(obj):\n    return obj.__globals__\n",
    "alias_import": "import subprocess as sp\n\ndef run():\n    sp.run(['echo'])\n",
    "alias_from": "from os import system as boom\n\ndef run():\n    boom('echo')\n",
    "getattr": "def run(obj):\n    return getattr(obj, 'system')('echo')\n",
    "ctypes": "import ctypes\nctypes.CDLL('libc.so.6')\n",
}


def test_safe_samples_are_allowed():
    for name, code in SAFE_SAMPLES.items():
        result = evaluate_code_policy(code)
        assert result.decision == "allow", name
        assert result.requires_approval is False


def test_approval_samples():
    for name, code in APPROVAL_SAMPLES.items():
        result = evaluate_code_policy(code)
        assert result.decision == "needs_approval", (name, result.reasons)
        assert result.requires_approval is True
        assert result.reasons


def test_deny_samples():
    for name, code in DENY_SAMPLES.items():
        result = evaluate_code_policy(code)
        assert result.decision == "deny", (name, result.reasons)


def test_import_os_without_a_dangerous_call_needs_approval():
    result = evaluate_code_policy("import os\nvalue = os.listdir('.')\n")
    assert result.decision == "needs_approval"


def test_syntax_error_and_empty_fail_closed():
    assert evaluate_code_policy("def (").decision == "deny"
    assert evaluate_code_policy("   ").decision == "deny"
    assert evaluate_code_policy("").decision == "deny"


def test_multiple_violations_prefer_deny():
    code = "import os\nos.system('x')\nopen('a')\n"
    result = evaluate_code_policy(code)
    assert result.decision == "deny"


def test_policy_does_not_execute_code(tmp_path: Path):
    marker = tmp_path / "should_not_exist.txt"
    code = (
        "from pathlib import Path\n"
        f"Path(r'{marker}').write_text('executed')\n"
    )
    result = evaluate_code_policy(code)
    assert result.decision == "needs_approval"
    assert not marker.exists()


def test_policy_is_deterministic():
    code = DENY_SAMPLES["alias_from"]
    assert evaluate_code_policy(code).model_dump() == evaluate_code_policy(code).model_dump()
