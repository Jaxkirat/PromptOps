"""AST policy engine.

``evaluate_code_policy`` parses Python with ``ast`` and never executes it.
A syntax error or empty module fails closed (deny).
"""

from __future__ import annotations

import ast

from codeforge.execution.models import POLICY_VERSION, PolicyResult

# Importing these modules is enough to deny: they exist to spawn processes,
# touch memory, or load arbitrary code.
_DENY_MODULES = {
    "subprocess",
    "ctypes",
    "multiprocessing",
    "pty",
    "mmap",
    "resource",
    "importlib",
}

# Importing these requires human approval (filesystem or network capability).
_APPROVAL_MODULES = {
    "socket",
    "urllib",
    "requests",
    "http",
    "httpx",
    "urllib3",
    "aiohttp",
    "ftplib",
    "smtplib",
    "ssl",
    "pathlib",
    "shutil",
    "os",
    "io",
}

_DENY_CALLS = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "breakpoint",
    "os.system",
    "os.popen",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "os.removedirs",
    "os.rename",
    "os.replace",
    "os.kill",
    "os.execl",
    "os.execle",
    "os.execlp",
    "os.execlpe",
    "os.execv",
    "os.execve",
    "os.execvp",
    "os.execvpe",
    "os.spawnl",
    "os.spawnle",
    "os.spawnlp",
    "os.spawnv",
    "os.spawnve",
    "os.spawnvp",
    "os._exit",
    "shutil.rmtree",
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.Popen",
    "subprocess.getoutput",
    "subprocess.getstatusoutput",
    "ctypes.CDLL",
    "ctypes.windll",
    "ctypes.cdll",
    "importlib.import_module",
    "importlib.__import__",
}

_APPROVAL_CALLS = {
    "open",
    "io.open",
    "pathlib.Path",
    "os.listdir",
    "os.scandir",
    "os.walk",
    "os.open",
    "os.read",
    "os.write",
    "os.mkdir",
    "os.makedirs",
    "os.chdir",
    "os.getcwd",
    "shutil.copy",
    "shutil.copy2",
    "shutil.copyfile",
    "shutil.move",
}

_DENY_DUNDERS = {
    "__globals__",
    "__builtins__",
    "__subclasses__",
    "__bases__",
    "__mro__",
    "__code__",
    "__closure__",
    "__dict__",
    "__class__",
}

_DANGEROUS_STRINGS = _DENY_CALLS | {
    "system",
    "rmtree",
    "Popen",
    "popen",
    "remove",
    "unlink",
    "eval",
    "exec",
}


def combine_policies(left: PolicyResult, right: PolicyResult) -> PolicyResult:
    """Keep the stricter decision. Deny wins over approval, which wins over allow."""
    rank = {"allow": 0, "needs_approval": 1, "deny": 2}
    decision = left.decision if rank[left.decision] >= rank[right.decision] else right.decision
    reasons = [
        reason
        for reason in [*left.reasons, *right.reasons]
        if "No restricted operations" not in reason
    ]
    if decision == "allow" and not reasons:
        reasons = ["No restricted operations detected."]
    return _result(
        decision,
        reasons,
        sorted(set(left.detected_operations) | set(right.detected_operations)),
        sorted(set(left.detected_imports) | set(right.detected_imports)),
    )


def evaluate_code_policy(code: str) -> PolicyResult:
    """Return allow, needs_approval, or deny. Never executes ``code``."""
    if code is None or not str(code).strip():
        return _result("deny", ["Empty code is denied (fail closed)."], [], [])

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return _result("deny", [f"Malformed Python (fail closed): {exc.msg}."], [], [])

    visitor = _PolicyVisitor()
    visitor.visit(tree)
    decision = "deny" if visitor.deny else "needs_approval" if visitor.approval else "allow"
    if decision == "allow" and not visitor.reasons:
        visitor.reasons.append("No restricted operations detected.")
    return _result(
        decision,
        visitor.reasons,
        sorted(visitor.operations),
        sorted(visitor.imports),
    )


def _result(
    decision: str, reasons: list[str], operations: list[str], imports: list[str]
) -> PolicyResult:
    deduped: list[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return PolicyResult(
        decision=decision,  # type: ignore[arg-type]
        reasons=deduped,
        detected_operations=operations,
        detected_imports=imports,
        policy_version=POLICY_VERSION,
        requires_approval=decision == "needs_approval",
    )


class _PolicyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.bindings: dict[str, str] = {}
        self.imports: set[str] = set()
        self.operations: set[str] = set()
        self.reasons: list[str] = []
        self.deny = False
        self.approval = False

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            root = alias.name.split(".")[0]
            self.bindings[local] = alias.name if "." in alias.name else root
            self.imports.add(alias.name)
            self._classify_import(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            if alias.name == "*":
                self._deny(f"Star import from {module or 'unknown'} is denied.")
                continue
            local = alias.asname or alias.name
            canonical = f"{module}.{alias.name}" if module else alias.name
            self.bindings[local] = canonical
            self.imports.add(canonical)
            self._classify_imported_symbol(module, alias.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        canonical = self._canonical(node.func)
        if canonical:
            self.operations.add(canonical)
            self._classify_call(canonical)
        if canonical in {"getattr", "setattr", "globals", "__import__", "importlib.import_module"}:
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if arg.value in _DANGEROUS_STRINGS or arg.value.split(".")[-1] in {
                        "system",
                        "rmtree",
                        "Popen",
                        "eval",
                        "exec",
                    }:
                        self._deny(
                            f"Dynamic lookup of dangerous operation '{arg.value}' is denied."
                        )
                        self.operations.add(f"dynamic:{arg.value}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in _DENY_DUNDERS:
            self._deny(f"Dunder escape via '{node.attr}' is denied.")
            self.operations.add(node.attr)
        canonical = self._canonical(node)
        if canonical:
            self._classify_call(canonical)
        self.generic_visit(node)

    def _classify_import(self, module_name: str) -> None:
        root = module_name.split(".")[0]
        if root in _DENY_MODULES or module_name in _DENY_MODULES:
            self._deny(f"Import of '{module_name}' is denied.")
            return
        if root in _APPROVAL_MODULES:
            self._approve(f"Import of '{module_name}' requires human approval.")

    def _classify_imported_symbol(self, module: str, name: str) -> None:
        root = module.split(".")[0] if module else ""
        canonical = f"{module}.{name}" if module else name
        if root in _DENY_MODULES or canonical in _DENY_CALLS or name in {"system", "rmtree", "Popen", "eval", "exec"}:
            if root in _DENY_MODULES or canonical in _DENY_CALLS or name in {"system", "rmtree", "Popen"}:
                self._deny(f"Import of '{canonical}' is denied.")
                return
        if name in {"eval", "exec", "compile", "__import__"}:
            self._deny(f"Import of '{canonical}' is denied.")
            return
        if root in _APPROVAL_MODULES or canonical in _APPROVAL_CALLS or name == "open":
            self._approve(f"Import of '{canonical}' requires human approval.")

    def _classify_call(self, canonical: str) -> None:
        base = canonical.split(".")[0]
        if canonical in _DENY_CALLS or base in _DENY_MODULES or canonical.startswith("subprocess."):
            self._deny(f"Call '{canonical}' is denied.")
            return
        if canonical.startswith("os.system") or canonical.startswith("os.exec") or canonical.startswith("os.spawn"):
            self._deny(f"Call '{canonical}' is denied.")
            return
        if canonical in {"os.remove", "os.unlink", "os.rmdir", "os.removedirs", "shutil.rmtree"}:
            self._deny(f"Call '{canonical}' is denied.")
            return
        if (
            canonical in _APPROVAL_CALLS
            or base in _APPROVAL_MODULES
            or canonical.startswith("pathlib.")
            or canonical.startswith("socket.")
            or canonical.startswith("urllib.")
            or canonical.startswith("requests.")
            or canonical.startswith("httpx.")
            or canonical.startswith("http.")
        ):
            self._approve(f"Call '{canonical}' requires human approval.")

    def _canonical(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return self.bindings.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = self._canonical(node.value)
            if not base:
                return node.attr
            return f"{base}.{node.attr}"
        return None

    def _deny(self, reason: str) -> None:
        self.deny = True
        self.reasons.append(reason)

    def _approve(self, reason: str) -> None:
        if self.deny:
            return
        self.approval = True
        self.reasons.append(reason)
