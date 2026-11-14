# CodeForge — Phase 1 (Level 1)

CodeForge is a multi-agent **Natural Language → Code** platform. You describe a
coding task in plain English; CodeForge classifies the request, extracts
structured requirements, generates a Python implementation, generates pytest
unit tests, **actually executes** those tests in an isolated subprocess, and
returns a structured report with the real results.

Built with **Python, LangChain, LangGraph and Pydantic**.

## Phase 1 Scope

Phase 1 implements the complete Level 1 pipeline:

- Router / Parser agent (python / sql / other classification)
- Requirements Extraction agent
- Code Generation agent
- Test Generation agent
- LangGraph orchestration with typed state and conditional edges
- Real pytest execution in an isolated subprocess with timeout
- Structured final report based on actual execution results

**Not implemented yet (by design):** R1 Identity & Privacy, R2 AST Policy Gate,
R3 Escalation & Human Handoff, R4 Cost/Latency Optimisation, R5 Resilience,
R6 Golden Set & Evaluation Gate, R7 Safe SQL Agent. SQL requests are correctly
*identified* but honestly reported as not implemented. See
[Future Integration Points](#future-integration-points-r1r7).

## Architecture Overview

Four single-responsibility agents are orchestrated by a LangGraph `StateGraph`
over a shared typed state (`CodeForgeState`). Execution and reporting are
separate stages behind clean interfaces.

```mermaid
flowchart TD
    START([START]) --> R[Router Agent<br/>classify request]
    R -->|python task| REQ[Requirements Agent<br/>structured requirements]
    R -->|sql / other / error| REP[Report Node<br/>structured final report]
    REQ -->|ok| CG[Code Generation Agent<br/>executable implementation]
    REQ -->|error| REP
    CG -->|ok| TG[Test Generation Agent<br/>pytest unit tests]
    CG -->|error| REP
    TG -->|ok| EX[Execution Node<br/>pytest in isolated subprocess]
    TG -->|error| REP
    EX --> REP
    REP --> END([END])
```

### Agent Responsibilities

| Component | File | Responsibility |
|---|---|---|
| Router Agent | `codeforge/agents/router_agent.py` | Classify the request as `python`, `sql` or `other` with confidence and reasoning (`RouterOutput`). |
| Requirements Agent | `codeforge/agents/requirements_agent.py` | Extract function name, parameters, return type, behaviour, edge cases and **explicit implementation constraints** (`RequirementsOutput`). Ambiguities become recorded assumptions. |
| Code Generation Agent | `codeforge/agents/code_generation_agent.py` | Produce executable, typed, documented Python honouring every constraint (`CodeOutput`). |
| Test Generation Agent | `codeforge/agents/test_generation_agent.py` | Produce an executable pytest module covering normal, boundary and edge cases plus requested constraints (`TestOutput`). |
| Execution Runner | `codeforge/execution/runner.py` | Write code + tests to a unique temp dir, run pytest in a **separate subprocess** with a timeout, parse the real results (`ExecutionResult`). |
| Reporter | `codeforge/execution/reporter.py` | Build the structured `FinalReport` from pipeline state; never conflates generation success with execution success. |

### LangGraph Workflow

- Typed state: `codeforge/graph/state.py` (`CodeForgeState` TypedDict)
- Nodes (one per stage): `codeforge/graph/nodes.py`
- Conditional edges: `codeforge/graph/edges.py` — non-Python tasks and any
  stage failure short-circuit to the report node, so callers always receive a
  structured report
- Assembly + public entry point: `codeforge/graph/workflow.py`

```python
from codeforge.graph.workflow import run_codeforge

result = run_codeforge("Write a function that checks whether a string is a palindrome.")
report = result["report"]   # pydantic FinalReport
print(report.status, report.execution.passed_tests)
```

## Project Structure

```
PromptOps/
├── codeforge/
│   ├── agents/                  # four single-responsibility agents
│   │   ├── _base.py             # shared structured-output invocation + error handling
│   │   ├── router_agent.py
│   │   ├── requirements_agent.py
│   │   ├── code_generation_agent.py
│   │   └── test_generation_agent.py
│   ├── graph/                   # LangGraph orchestration
│   │   ├── state.py             # CodeForgeState TypedDict
│   │   ├── nodes.py             # node callables wrapping agents/runner/reporter
│   │   ├── edges.py             # conditional edge functions
│   │   └── workflow.py          # graph assembly + run_codeforge()
│   ├── models/
│   │   ├── schemas.py           # all Pydantic structured-output schemas
│   │   └── llm_factory.py       # provider-agnostic chat-model factory
│   ├── execution/
│   │   ├── runner.py            # subprocess pytest runner (temp dir + timeout)
│   │   └── reporter.py          # FinalReport builder + CLI formatter
│   ├── prompts/                 # all prompt templates (none inside agent files)
│   ├── config/
│   │   └── settings.py          # centralised env-based configuration
│   └── exceptions.py
├── tests/                       # mocked-LLM unit + integration tests
├── examples/sample_requests.py
├── main.py                      # interactive CLI
├── requirements.txt             # pinned dependencies
├── pytest.ini
├── .env.example                 # all supported config variables (committed)
├── .env                         # your local credentials (git-ignored)
└── README.md
```

## Technology Stack

- Python 3.12 (3.11+ compatible)
- LangChain 1.5 / langchain-openai 1.8 — LLM integration & structured output
- LangGraph 1.2 — stateful agent orchestration
- Pydantic 2.14 — schemas and validation
- pytest 9 — test generation target and project test runner
- python-dotenv — environment configuration

## Setup

### 1. Create and activate a virtual environment

```powershell
# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

```bash
# Linux / macOS
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure LLM credentials

Copy `.env.example` to `.env` (a template `.env` is already created) and enter
your credentials. **Only the selected provider's key is required.**

```dotenv
LLM_PROVIDER=openai          # openai | anthropic | google
LLM_MODEL=gpt-4.1-mini
LLM_API_KEY=sk-...           # generic key (preferred), or use the provider-specific one:
OPENAI_API_KEY=
```

- `LLM_BASE_URL` — optional custom endpoint (e.g. an OpenAI-compatible proxy).
- For `anthropic` / `google`, also install the optional integration package
  listed at the bottom of `requirements.txt`.
- `.env` is git-ignored; credentials are never hardcoded or logged.

Additional settings: `EXECUTION_TIMEOUT_SECONDS` (default 15),
`MAX_TEST_OUTPUT_LENGTH` (default 10000), `LOG_LEVEL`, `APP_ENV`.

## Running CodeForge

```bash
python main.py
```

The CLI accepts multiple requests in one session (`exit` / `quit` to leave).
If the LLM configuration is incomplete, a clear error explains what to set.

Example session:

```
==================================================
                 CODEFORGE
       Natural Language to Code Platform
==================================================

Enter your coding request:
> If I pass a list, return its sum using a list comprehension; if a tuple, use functional programming.

[1/6] Routing request...
[2/6] Extracting requirements...
[3/6] Generating code...
[4/6] Generating unit tests...
[5/6] Executing tests...
[6/6] Preparing report...

==================================================
                   FINAL REPORT
==================================================
Task Type:  python
Status:     SUCCESS
Detail:     All 9 generated tests passed in actual pytest execution.

Generated Code:    ...
Generated Tests:   ...
Test Results (actual pytest execution):
  9 passed, 0 failed, 0 skipped (exit code: 0)
  Execution Time: 3.09s
==================================================
```

An SQL request is identified and reported honestly:

```
Status:     UNSUPPORTED
Detail:     SQL request correctly identified, but SQL execution is not implemented
            in Phase 1 (planned: R7 Safe SQL Agent). No code was generated or executed.
```

You can also run the bundled demo requests: `python -m examples.sample_requests`

## Running the Tests

```bash
python -m pytest tests -v
```

The suite (46 tests) uses **mocked LLMs** — no API calls, no credentials
needed. Generated code/tests in the end-to-end suite still run through the
**real** subprocess pytest runner, so reports are verified against actual
execution. Covered: schema validation, all four agents (including malformed /
empty / failing LLM responses), graph transitions and error propagation, the
execution runner (pass / fail / syntax error / timeout / no-tests / output
truncation), and six end-to-end scenarios (flagship list/tuple sum,
palindrome, factorial, Fibonacci, SQL, non-coding request).

## Current Limitations

- Only Python tasks are executed; SQL and other languages are identified but
  reported as unsupported.
- The execution runner uses a subprocess + temp directory + timeout as
  **baseline development safeguards only** — it is *not* a production-secure
  sandbox (no syscall/network/filesystem isolation). Hardening arrives with R2.
- No retries, fallbacks or circuit breakers on LLM calls (R5).
- No evaluation gate on output quality (R6); generated tests may occasionally
  fail, and the report will say so honestly.
- Single LLM for all agents (model cascade arrives with R4).

## Future Integration Points (R1–R7)

The architecture reserves clean insertion points so later phases need no major
refactor:

| Phase | Insertion point |
|---|---|
| R1 Identity & Privacy | Middleware before the `router` node (pre-processing of `user_request` in state). |
| R2 AST Policy Gate | New node between `test_generation` and `execution`; all execution already flows through the single `PytestRunner.run` interface, which a hardened sandbox can replace. |
| R3 Escalation / Human Handoff | LangGraph interrupt/approval node via conditional edges (edges are centralised in `graph/edges.py`). |
| R4 Cost & Latency | Model cascade inside `models/llm_factory.py`; agents only depend on `BaseChatModel`. |
| R5 Resilience | Retry/fallback wrappers around `agents/_base.invoke_structured`, the single LLM call site. |
| R6 Evaluation Gate | Consumes the structured `FinalReport` / `ExecutionResult` already produced for every run. |
| R7 Safe SQL Agent | New branch from the router's existing conditional edge (`task_type == "sql"`). |
