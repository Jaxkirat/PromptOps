"""Mask every string cell before a result is returned or logged."""

from __future__ import annotations

from codeforge.privacy.masker import mask_sensitive_data
from codeforge.sql_agent.allowlist import SENSITIVE_COLUMNS
from codeforge.sql_agent.models import AccessScope, QueryResult


def redact_results(result: QueryResult, scope: AccessScope, *, enforce_runs: bool) -> QueryResult:
    if not result.ok:
        return result
    kept_indexes = [
        index for index, name in enumerate(result.columns) if name.lower() not in SENSITIVE_COLUMNS
    ]
    columns = [result.columns[index] for index in kept_indexes]
    rows: list[list] = []
    run_index = columns.index("run_id") if "run_id" in columns else None
    allowed_runs = set(scope.run_ids)
    for source in result.rows:
        if enforce_runs and run_index is not None:
            run_id = source[result.columns.index("run_id")]
            if run_id not in allowed_runs:
                return QueryResult(ok=False, category="scope_violation", executed=True)
        cleaned = []
        for index in kept_indexes:
            value = source[index]
            if isinstance(value, str):
                cleaned.append(mask_sensitive_data(value).sanitized_text)
            else:
                cleaned.append(value)
        rows.append(cleaned)
    return QueryResult(
        ok=True,
        columns=columns,
        rows=rows,
        truncated=result.truncated,
        executed=result.executed,
    )
