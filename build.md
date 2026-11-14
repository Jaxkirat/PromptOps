# CODEFORGE — PHASE 1 IMPLEMENTATION
## Build the complete Level 1 Multi-Agent NL-to-Code Pipeline

Act as a senior AI engineer and software architect. Your task is to implement Phase 1 of CodeForge, a production-oriented multi-agent Natural Language-to-Code system, using Python, LangChain, LangGraph and Pydantic.

This is part of a hackathon project. The architecture must be clean, modular, testable, extensible and demonstrable.

Do not build a throwaway prototype. Build a solid foundation that we can extend with security, resilience, cost optimisation, evaluation and SQL capabilities in subsequent phases.

---

# 1. PROJECT OBJECTIVE

Build a multi-agent system that accepts a natural-language coding request and performs the following workflow:

1. Router / Parser Agent
2. Requirements Extraction Agent
3. Code Generation Agent
4. Test Generation Agent
5. LangGraph Orchestrator
6. Execute generated tests.
7. Return a structured execution report containing the actual results.

Example input:

"If I pass a list, return its sum using a list comprehension; if a tuple, use functional programming."

Expected output:
- Correctly classified as a Python programming task.
- Extracted structured requirements.
- Python implementation satisfying the requirements.
- Pytest-style unit tests.
- Actual test execution.
- Execution report showing the generated code, tests, number of passed tests, failed tests and execution status.

The system must be functional end-to-end.

# 2. IMPORTANT IMPLEMENTATION BOUNDARIES

For this phase, implement ONLY Level 1.

Do not implement:
- R1 Identity and Privacy.
- R2 AST-based Policy Gate.
- R3 Escalation and Human Handoff.
- R4 Cost and Latency Optimisation.
- R5 Resilience.
- R6 Golden Set and Evaluation Gate.
- R7 Safe SQL Agent.

However, design the architecture so these components can be introduced later without requiring a major refactor.

For example:
- A future privacy middleware should be insertable before the Router.
- A future triage agent should be insertable before the main pipeline.
- A future policy gate should sit between test generation and execution.
- A future human approval node should be supported through LangGraph.
- A future model cascade should be configurable at the LLM abstraction layer.
- A future evaluation system should be able to inspect structured execution results.

Do not prematurely implement these features.

# 3. TECHNOLOGY STACK

Use the following technologies:

- Python 3.11 or compatible stable Python version.
- LangChain for LLM integration.
- LangGraph for agent orchestration.
- Pydantic for structured outputs and validation.
- Pytest for test execution.
- python-dotenv for environment configuration.
- A configurable LLM provider abstraction.

Prefer modern, stable versions of the libraries. Pin dependency versions in the project dependency file.

Use Python type hints throughout the project.

Avoid unnecessary dependencies.

# 4. PROJECT STRUCTURE

First inspect the existing repository.

Preserve existing useful files and code. Do not blindly overwrite the repository.

Create a modular structure similar to the following:

codeforge/
│
├── agents/
│   ├── __init__.py
│   ├── router_agent.py
│   ├── requirements_agent.py
│   ├── code_generation_agent.py
│   └── test_generation_agent.py
│
├── graph/
│   ├── __init__.py
│   ├── state.py
│   ├── nodes.py
│   ├── workflow.py
│   └── edges.py
│
├── models/
│   ├── __init__.py
│   ├── schemas.py
│   └── llm_factory.py
│
├── execution/
│   ├── __init__.py
│   ├── runner.py
│   └── reporter.py
│
├── prompts/
│   ├── router.py
│   ├── requirements.py
│   ├── code_generation.py
│   └── test_generation.py
│
├── config/
│   ├── __init__.py
│   └── settings.py
│
├── tests/
│   ├── test_schemas.py
│   ├── test_agents.py
│   ├── test_graph.py
│   ├── test_execution.py
│   └── test_end_to_end.py
│
├── examples/
│   └── sample_requests.py
│
├── .env.example
├── .env
├── .gitignore
├── requirements.txt
├── README.md
└── main.py

You can adjust this structure if there is a strong architectural reason, but maintain clear separation of responsibilities.

Do not create one giant Python file containing all agents.

# 5. ENVIRONMENT AND LLM CONFIGURATION

This is mandatory.

Create a proper Python virtual environment inside the project.

Use:

python -m venv .venv

The project must support Windows PowerShell and Unix-based environments.

Provide activation instructions.

Windows PowerShell:
.venv\Scripts\Activate.ps1

Linux/macOS:
source .venv/bin/activate

Create requirements.txt containing all necessary dependencies.

Create TWO environment files:

1. .env.example
2. .env

The .env.example must contain all supported configuration variables with placeholder values.

The .env file should be created if it does not already exist. Never overwrite an existing .env file or destroy credentials already entered by the developer.

Suggested configuration:

# LLM Provider
LLM_PROVIDER=openai
LLM_MODEL=gpt-4.1-mini
LLM_API_KEY=
LLM_BASE_URL=

# Optional provider configurations
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=

# Application
APP_ENV=development
LOG_LEVEL=INFO

# Execution
EXECUTION_TIMEOUT_SECONDS=15
MAX_TEST_OUTPUT_LENGTH=10000

The configuration must be provider-agnostic.

Implement an LLM factory that can initialise the configured provider.

At minimum, support OpenAI through LangChain's ChatOpenAI integration.

Structure the factory so Anthropic and Google Gemini can be added without changing individual agent implementations.

Use the correct provider-specific API key and model configuration.

Important:
- Do not hardcode credentials anywhere.
- Do not expose API keys in logs.
- Never commit .env.
- Add .env to .gitignore.
- Add .env.example to version control.
- Validate missing credentials at startup and provide a clear error message.
- Do not require all providers' API keys. Only the selected provider's credentials should be required.
- Keep provider-specific dependencies organised.

I should be able to enter my LLM credentials in .env and run the application without modifying Python source code.

# 6. PYDANTIC STRUCTURED OUTPUT SCHEMAS

Implement reusable Pydantic schemas in models/schemas.py.

All agents must return validated structured data instead of unstructured text.

## A. RouterOutput

Fields:

- task_type: Literal["python", "sql", "other"]
- language: str
- description: str
- confidence: float
- reasoning: str

The router must identify:
- Python programming requests.
- SQL requests.
- Other programming languages or unsupported task types.

Default to Python when the request does not explicitly specify another language and is clearly a coding task.

SQL must be correctly identified, but SQL execution and the dedicated SQL agent are OUT OF SCOPE for Phase 1.

The router must not pretend SQL functionality is implemented.

## B. RequirementsOutput

Fields:

- task_type: str
- language: str
- function_name: str
- description: str
- parameters: list of parameter objects
- return_type: str
- expected_behavior: list[str]
- edge_cases: list[str]
- constraints: list[str]
- implementation_notes: list[str]

Each parameter object should contain:
- name
- data_type
- description
- required

Extract requirements accurately from natural-language instructions.

Do not invent requirements that the user did not specify.

If something is ambiguous, make reasonable assumptions and record them explicitly.

## C. CodeOutput

Fields:

- language: str
- code: str
- explanation: str
- dependencies: list[str]
- implementation_notes: list[str]

The code field must contain executable source code without Markdown code fences.

## D. TestOutput

Fields:

- language: str
- test_framework: str
- test_code: str
- test_cases: list of test case descriptions

For Python tasks:
- Use pytest.
- Generate independent unit tests.
- Cover normal inputs.
- Cover boundary conditions.
- Cover edge cases.
- Cover explicitly requested implementation constraints.
- Do not generate tests that merely reproduce the implementation logic.
- Avoid tests that assume unspecified behaviour.

Use Pydantic validation to ensure outputs follow these schemas.

# 7. IMPLEMENT THE FOUR AGENTS

Each agent must be a separate class or function with a clearly defined responsibility.

## AGENT 1: ROUTER / PARSER

File: agents/router_agent.py

Responsibilities:

1. Accept the original user request.
2. Identify the programming task.
3. Identify the programming language.
4. Classify it as Python, SQL or other.
5. Produce a RouterOutput object.

Use LLM structured output.

Do not rely on simple keyword matching as the primary classification mechanism.

Include clear system instructions and handle malformed LLM responses appropriately.

## AGENT 2: REQUIREMENTS EXTRACTION

File: agents/requirements_agent.py

Responsibilities:

1. Accept the original request and router output.
2. Extract the actual programming requirements.
3. Identify the function name.
4. Identify parameters and their types.
5. Identify expected return values.
6. Identify expected behaviour.
7. Identify edge cases.
8. Capture implementation constraints.
9. Return a validated RequirementsOutput object.

The agent must preserve specific implementation instructions.

Example:

"If I pass a list, return its sum using a list comprehension; if a tuple, use functional programming."

The requirements must explicitly capture:
- List input uses a list comprehension.
- Tuple input uses functional programming.
- Both inputs return the sum.
- Relevant invalid or empty input behaviour should be specified or recorded as an assumption.

Do not lose these implementation details during requirement extraction.

## AGENT 3: CODE GENERATION

File: agents/code_generation_agent.py

Responsibilities:

1. Accept RequirementsOutput.
2. Generate implementation code.
3. Follow every explicit implementation constraint.
4. Generate readable, maintainable code.
5. Include appropriate type hints.
6. Include docstrings where useful.
7. Handle edge cases.
8. Avoid unnecessary dependencies.

Return CodeOutput.

Important:
- The code must be actual executable source code.
- Do not wrap the code in Markdown fences.
- Do not generate placeholder implementations.
- Do not claim functionality that has not been implemented.
- The implementation must satisfy the extracted requirements.

## AGENT 4: TEST GENERATION

File: agents/test_generation_agent.py

Responsibilities:

1. Accept RequirementsOutput and CodeOutput.
2. Generate pytest-compatible unit tests.
3. Cover normal and edge cases.
4. Validate the intended functionality.
5. Validate explicitly requested implementation constraints wherever practical.
6. Avoid tautological tests.
7. Return TestOutput.

For Python, generate a complete pytest test module.

The generated tests must be executable.

Make sure the generated tests correctly import or access the implementation under test.

Avoid hardcoding assumptions that are absent from the requirements.

# 8. LANGGRAPH ORCHESTRATION

Files:
- graph/state.py
- graph/nodes.py
- graph/edges.py
- graph/workflow.py

This is a central architectural requirement.

Use LangGraph StateGraph with a clearly defined TypedDict state.

The graph must connect the four agents and the execution stage.

Suggested flow:

START
  |
  v
Router Agent
  |
  v
Requirements Agent
  |
  v
Code Generation Agent
  |
  v
Test Generation Agent
  |
  v
Execution Node
  |
  v
Report Node
  |
  v
END

Implement the workflow using separate graph nodes.

Do not place all agent logic inside one LangGraph node.

State must retain:

- Original user request.
- Router output.
- Requirements output.
- Generated code.
- Generated tests.
- Execution result.
- Final report.
- Errors and relevant metadata.

Use structured state updates.

The graph should support:
- Sequential execution.
- Error propagation.
- Clear failure states.
- Intermediate state inspection.
- Future conditional edges.

If routing identifies SQL or an unsupported language, do not send the request through a Python pytest execution path incorrectly. Return an honest, structured unsupported/not-yet-implemented result.

Use LangGraph's normal compilation and invocation mechanisms.

Expose a clean public function such as:

run_codeforge(user_request: str) -> dict

This should be the primary programmatic entry point.

# 9. CODE AND TEST EXECUTION

File: execution/runner.py

The generated Python code and pytest tests must actually run.

Implement a development-stage execution runner.

Requirements:

1. Create a unique temporary working directory for each execution.
2. Write generated implementation code to a Python source file.
3. Write generated tests to a separate pytest test file.
4. Execute pytest in a separate subprocess.
5. Capture stdout and stderr.
6. Capture the actual process exit code.
7. Implement a configurable execution timeout.
8. Clean up temporary files after execution.
9. Return a structured execution result.

Suggested result schema:

ExecutionResult:
- status
- exit_code
- total_tests
- passed_tests
- failed_tests
- skipped_tests
- stdout
- stderr
- execution_time_seconds
- timed_out
- error_message

The result must be based on actual pytest execution.

Never claim that tests passed because the LLM says they passed.

The only condition for a successful test execution is an actual successful pytest exit code.

Important security limitation:

This is Phase 1, before R2.

Use a separate subprocess, temporary directory and timeout as baseline development safeguards. Do not claim this is a production-secure sandbox.

Do not execute arbitrary code in the main application process.

Keep the execution runner behind a clean interface so the R2 policy gate and stronger sandbox can be inserted before it in a later phase.

Do not silently auto-approve code requiring elevated permissions. Do not add network access to the execution environment.

# 10. REPORTING

File: execution/reporter.py

Generate a structured final report.

The report should contain:

- Original user request.
- Detected task type.
- Detected language.
- Extracted requirements.
- Generated implementation.
- Generated tests.
- Actual execution status.
- Test counts.
- Execution time.
- Relevant errors.

The report must distinguish:
- Generation successful.
- Execution successful.
- Tests passed.
- Tests failed.
- Execution timed out.
- Unsupported task.

Do not confuse successful code generation with successful code execution.

Use a reusable Pydantic report schema.

# 11. ERROR HANDLING

Implement proper error handling throughout the pipeline.

Handle:
- Missing API credentials.
- LLM API failures.
- Rate limits.
- Invalid structured outputs.
- Pydantic validation failures.
- Empty model responses.
- Code generation failures.
- Test generation failures.
- Subprocess errors.
- Pytest failures.
- Execution timeouts.
- Unsupported task types.

For this phase, errors should be captured and returned in structured form.

Do not implement the full R5 retry, fallback or circuit-breaker system yet.

Do not swallow exceptions silently.

Use meaningful error messages and appropriate logging.

Never log API credentials.

# 12. MAIN APPLICATION ENTRY POINT

File: main.py

Provide a simple CLI interface.

Example:

python main.py

Expected interaction:

==================================================
                 CODEFORGE
       Natural Language to Code Platform
==================================================

Enter your coding request:

> Write a function that checks whether a string
  is a palindrome.

[1/6] Routing request...
[2/6] Extracting requirements...
[3/6] Generating code...
[4/6] Generating unit tests...
[5/6] Executing tests...
[6/6] Preparing report...

==================================================
                  FINAL REPORT
==================================================

Task Type: Python
Language: Python
Status: SUCCESS

Generated Code:
...

Generated Tests:
...

Test Results:
5 passed, 0 failed

Execution Time: ...

==================================================

This is an illustrative interface. Actual results must be displayed.

The CLI must allow multiple requests without restarting the application.

Provide clear errors when the LLM configuration is incomplete.

# 13. TESTING

Write unit and integration tests for the project itself.

Do not depend on live API calls for ordinary automated tests.

Use mocked LLM responses to test:
- Router output.
- Requirements extraction.
- Code generation.
- Test generation.
- Schema validation.
- Graph transitions.
- Error handling.

Test the execution runner independently using known safe sample code and tests.

Create an end-to-end integration test using mocked agents or a mocked LLM.

The following test scenario must work:

INPUT:

"If I pass a list, return its sum using a list comprehension; if a tuple, use functional programming."

EXPECTED FUNCTIONALITY:

- A Python task is detected.
- Requirements are extracted.
- Both list and tuple behaviour are represented.
- The implementation follows the list-comprehension constraint for lists.
- The implementation uses functional programming for tuples.
- Pytest tests are generated.
- The tests execute successfully.
- The final report reflects actual pytest results.

Also test at least:
1. A simple palindrome request.
2. A factorial request.
3. A Fibonacci request.
4. An SQL request, which must be identified but honestly reported as not implemented in this phase.
5. An unsupported non-coding request, which must not be treated as a Python function-generation request.

# 14. CODE QUALITY REQUIREMENTS

Follow these principles:

- Separation of concerns.
- Single responsibility per agent.
- Reusable classes and functions.
- Type hints.
- Pydantic validation.
- Meaningful naming.
- Proper docstrings.
- Centralised configuration.
- No hardcoded API credentials.
- No unnecessary global state.
- No giant prompts embedded directly inside agent implementation files.
- Keep prompts in the prompts directory.
- Keep all model initialisation in the LLM factory.
- Keep orchestration separate from agent logic.
- Keep execution separate from code generation.
- Keep reporting separate from execution.

Do not overengineer.

Prefer straightforward, readable implementations over unnecessary abstractions.

# 15. README DOCUMENTATION

Create a complete README.md explaining:

1. What CodeForge is.
2. Phase 1 scope.
3. Architecture overview.
4. Responsibilities of each agent.
5. LangGraph workflow.
6. Project structure.
7. Technology stack.
8. Python virtual environment setup.
9. Dependency installation.
10. Environment variable configuration.
11. How to configure LLM credentials.
12. How to run the application.
13. How to run tests.
14. Example input and expected output.
15. Current limitations.
16. Planned future integration points for R1-R7.

Include a Mermaid flowchart of the LangGraph pipeline.

Clearly document that R1-R7 are not yet implemented in Phase 1.

# 16. IMPLEMENTATION WORKFLOW

Follow this sequence:

STEP 1:
Inspect the current repository and identify its existing structure and dependencies.

STEP 2:
Create the virtual environment and project configuration.

STEP 3:
Create .env.example, .env and .gitignore safely.

STEP 4:
Implement Pydantic schemas and LLM factory.

STEP 5:
Implement the four agents independently.

STEP 6:
Implement LangGraph typed state, nodes and workflow.

STEP 7:
Implement the execution runner and reporter.

STEP 8:
Implement the CLI.

STEP 9:
Write and run automated tests.

STEP 10:
Run the complete sample request end-to-end using the configured LLM.

STEP 11:
Fix all implementation and testing issues.

STEP 12:
Update the README.

Do not stop after creating files or scaffolding. Implement the actual functionality.

Do not mark a task as complete until you have verified it.

# 17. FINAL ACCEPTANCE CRITERIA

The implementation is considered complete only when:

[ ] A working Python virtual environment exists.

[ ] All dependencies are documented and installable.

[ ] .env.example exists.

[ ] .env exists without overwriting existing credentials.

[ ] .env is excluded from Git.

[ ] LLM credentials are loaded from environment variables.

[ ] The Router produces validated structured output.

[ ] The Requirements Agent produces validated structured output.

[ ] The Code Generation Agent generates actual executable code.

[ ] The Test Generation Agent generates actual pytest tests.

[ ] All four agents are separate components.

[ ] LangGraph connects the agents using typed state.

[ ] The workflow can execute end-to-end.

[ ] Generated tests actually execute through pytest.

[ ] Actual test results are reflected in the final report.

[ ] SQL is identified but not falsely presented as implemented.

[ ] Unsupported tasks are handled honestly.

[ ] Unit and integration tests pass.

[ ] README contains complete setup and execution instructions.

[ ] Future R1-R7 integration points are documented.

[ ] No credentials are hardcoded or committed.

[ ] No generated code executes inside the main application process.

# 18. HOW TO WORK WITH ME

Work directly in the currently opened repository.

Before making changes:
- Inspect the repository.
- Identify existing code worth preserving.
- Present a brief implementation plan.
- Identify any existing conflicts with the proposed structure.

Then implement the project.

You may make sensible engineering decisions without repeatedly asking for approval.

However:
- Do not silently change the scope.
- Do not implement R1-R7 prematurely.
- Do not substitute mocked functionality for actual functionality in the application.
- Mocks are permitted in automated tests.
- Do not claim end-to-end success without actually running the workflow.

At the end, provide:

1. Summary of what was implemented.
2. Final project directory structure.
3. Virtual environment setup commands.
4. Dependency installation commands.
5. Exact instructions for entering LLM credentials.
6. Exact command to launch CodeForge.
7. Exact command to run automated tests.
8. Test execution results.
9. Any remaining limitations or unresolved issues.
10. Recommended next implementation phase.

The most important objective:

**Deliver a working, modular Level 1 CodeForge pipeline that can reliably transform natural language into code, generate tests, execute those tests and report the real results.**

Build the foundation correctly. Every subsequent hackathon requirement will build on this implementation.