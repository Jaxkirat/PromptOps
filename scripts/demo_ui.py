"""Phase 3 live demonstrations (build_UI.md section 25).

Uses the real application services and Gradio handlers. Demo 3 optionally
runs the live LangGraph pipeline when LLM credentials are present.

    python scripts/demo_ui.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DEMO_DB = Path("./demo_ui.db")
if DEMO_DB.exists():
    DEMO_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{DEMO_DB.as_posix()}"
os.environ["MAX_RUNS_PER_USER_PER_DAY"] = "3"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codeforge.config.settings import get_settings  # noqa: E402
from codeforge.database.database import init_db, reset_database_state  # noqa: E402
from codeforge.services.invitation_service import create_instructor_invitation  # noqa: E402
from codeforge.services.run_service import set_pipeline_runner  # noqa: E402
from codeforge.ui.formatters import assistant_message, requirements_markdown, tests_summary_markdown  # noqa: E402
from codeforge.ui.handlers import (  # noqa: E402
    handle_accept_invite,
    handle_history,
    handle_load_run,
    handle_login,
    handle_logout,
    handle_quota,
    handle_register,
    handle_submit,
    new_session,
)
from tests.conftest import FakePipeline  # noqa: E402
from tests.test_invitations import _raw_token_from_url  # noqa: E402

get_settings.cache_clear()
reset_database_state()
init_db()
PASSWORD = "StrongPassword123"
results: list[tuple[str, bool, str]] = []


def check(demo: str, passed: bool, detail: str) -> None:
    results.append((demo, passed, detail))
    print(f"  {'PASS' if passed else 'FAIL'}: {detail}")


print("\n=== DEMO 1: STUDENT REGISTRATION ===")
session = new_session()
session, error = handle_register(
    session, "Student Demo", "demo-student@example.com", PASSWORD, PASSWORD
)
check(
    "DEMO 1",
    error == "" and session["profile"].role == "student" and session["adapter"].is_authenticated,
    f"error={error!r} role={getattr(session['profile'], 'role', None)}",
)

print("\n=== DEMO 2: INSTRUCTOR INVITATION ===")
created = create_instructor_invitation("demo-instructor@example.com")
token = _raw_token_from_url(created.invite_url)
invite_session, error = handle_accept_invite(
    new_session(), token, "Instructor Demo", "demo-instructor@example.com", PASSWORD, PASSWORD
)
reuse_session, reuse_error = handle_accept_invite(
    new_session(), token, "Instructor Demo", "demo-instructor@example.com", PASSWORD, PASSWORD
)
check(
    "DEMO 2",
    error == ""
    and invite_session["profile"].role == "instructor"
    and "already been used" in reuse_error.lower(),
    f"role={getattr(invite_session['profile'], 'role', None)} reuse={reuse_error!r}",
)

print("\n=== DEMO 3: CODE GENERATION ===")
pipeline = FakePipeline()
live = False
try:
    from codeforge.models.llm_factory import validate_llm_config

    validate_llm_config()
    from codeforge.graph.workflow import build_workflow

    graph = build_workflow()
    set_pipeline_runner(lambda text: graph.invoke({"user_request": text}))
    live = True
    print("  using live LangGraph pipeline")
except Exception as exc:
    set_pipeline_runner(pipeline)
    print(f"  using fake pipeline ({exc.__class__.__name__})")

session, _, _ = handle_submit(
    session,
    "If I pass a list, return its sum using a list comprehension; if a tuple, use functional programming.",
)
run = session["current_run"]
has_code = bool(run and run.generated_code)
has_tests = bool(run and run.generated_tests)
has_req = "function" in requirements_markdown(run).lower() if run else False
summary = tests_summary_markdown(run) if run else ""
message = assistant_message(run) if run else ""
check(
    "DEMO 3",
    run is not None and has_code and has_tests and has_req and run.status in {"success", "tests_failed", "unsupported"},
    f"status={getattr(run, 'status', None)} code={has_code} tests={has_tests} "
    f"requirements={has_req} live={live} summary={summary[:60]!r}",
)

print("\n=== DEMO 4: RUN HISTORY ===")
set_pipeline_runner(pipeline)
handle_submit(session, "Write a palindrome checker")
handle_submit(session, "Write a factorial function")
runs = handle_history(session)
first_id = runs[-1].id if runs else ""
session, load_error = handle_load_run(session, first_id)
check(
    "DEMO 4",
    len(runs) >= 2 and load_error == "" and session["current_run"].id == first_id,
    f"history={len(runs)} loaded={getattr(session['current_run'], 'id', None)}",
)

print("\n=== DEMO 5: ROLE DIFFERENTIATION ===")
student_role = session["profile"].role
instructor_role = invite_session["profile"].role
from codeforge.ui.handlers import instructor_sql_notice

notice = instructor_sql_notice()
check(
    "DEMO 5",
    student_role == "student"
    and instructor_role == "instructor"
    and "R7" in notice
    and "not implemented" in notice.lower(),
    f"student={student_role} instructor={instructor_role}",
)

print("\n=== DEMO 6: SESSION ISOLATION ===")
user_b, _ = handle_register(new_session(), "B", "demo-b@example.com", PASSWORD, PASSWORD)
handle_submit(user_b, "only for B")
hist_a = [r.sanitised_request for r in handle_history(session)]
hist_b = [r.sanitised_request for r in handle_history(user_b)]
session_logged_out = handle_logout(session)
check(
    "DEMO 6",
    "only for B" not in " ".join(hist_a)
    and all("only for B" in item for item in hist_b)
    and not session_logged_out["adapter"].is_authenticated
    and user_b["adapter"].is_authenticated,
    f"A_count={len(hist_a)} B_count={len(hist_b)} A_logged_out={not session_logged_out['adapter'].is_authenticated}",
)

print("\n=== DEMO 7: QUOTA HANDLING ===")
from codeforge.config.settings import get_settings as _gs

os.environ["MAX_RUNS_PER_USER_PER_DAY"] = "1"
_gs.cache_clear()
quota_user, _ = handle_register(new_session(), "Q", "demo-quota@example.com", PASSWORD, PASSWORD)
quota_user, kind1, _ = handle_submit(quota_user, "first allowed")
calls_before = len(pipeline.calls)
quota_user, kind2, err2 = handle_submit(quota_user, "should reject")
check(
    "DEMO 7",
    kind1 == "ok" and kind2 == "quota" and "quota" in err2.lower() and len(pipeline.calls) == calls_before,
    f"kinds={kind1},{kind2} extra_pipeline_calls={len(pipeline.calls) - calls_before}",
)
os.environ["MAX_RUNS_PER_USER_PER_DAY"] = "3"
_gs.cache_clear()

print("\n=== DEMO 8: UNSUPPORTED TASK ===")
from tests.test_ui_integration import UnsupportedPipeline

set_pipeline_runner(UnsupportedPipeline("other"))
other, _ = handle_register(new_session(), "O", "demo-other@example.com", PASSWORD, PASSWORD)
other, kind, _ = handle_submit(other, "What is the capital of France?")
run8 = other["current_run"]
msg8 = assistant_message(run8)
check(
    "DEMO 8",
    kind == "ok"
    and run8.status == "unsupported"
    and not run8.generated_code
    and "No Python function was generated" in msg8,
    f"status={run8.status} code={bool(run8.generated_code)}",
)

print("\n" + "=" * 60)
all_passed = all(ok for _, ok, _ in results)
for demo, ok, _ in results:
    print(f"  {demo}: {'PASS' if ok else 'FAIL'}")
print("=" * 60)
print("ALL UI DEMOS PASSED" if all_passed else "SOME UI DEMOS FAILED")
sys.exit(0 if all_passed else 1)
