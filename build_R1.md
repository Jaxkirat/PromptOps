# CODEFORGE — PHASE 2
# R1: IDENTITY, PRIVACY, AUTHENTICATION AND BACKEND ARCHITECTURE
## Prepare the existing CodeForge system for Gradio UI integration

Act as a senior AI architect, Python backend engineer and application security engineer.

You are working on CodeForge, an existing multi-agent Natural Language-to-Code application.

PHASE 1 HAS BEEN IMPLEMENTED AND VERIFIED.

The existing system includes:

- Router / Parser Agent.
- Requirements Extraction Agent.
- Code Generation Agent.
- Test Generation Agent.
- LangGraph orchestration.
- Pydantic structured outputs.
- Configurable LLM provider.
- Python execution runner.
- Pytest execution.
- Structured execution reports.
- CLI interface.
- Existing FastAPI application/routes, if already implemented.

Your task is to implement PHASE 2: R1 Identity and Privacy.

Additionally, establish a clean backend architecture that will allow us to build and integrate a Gradio UI in Phase 3.

IMPORTANT ARCHITECTURAL DECISION:

We are NOT building a separate React frontend.

Gradio will be our primary user interface.

However, retain FastAPI as the backend API layer. The existing FastAPI endpoints must remain usable by the future Gradio interface.

We want a single application architecture in which FastAPI and Gradio can coexist.

The intended final architecture is:

Gradio UI
    |
    v
FastAPI Application
    |
    ├── Authentication
    ├── Authorization
    ├── User Management
    ├── Privacy / PII Masking
    ├── Quota Management
    ├── Run History
    |
    v
Shared CodeForge Service Layer
    |
    v
LangGraph Workflow
    |
    v
Existing Multi-Agent Pipeline

The Gradio interface will be implemented in the NEXT PHASE.

Do not build the actual Gradio UI now.

Your responsibility in this phase is to make the backend and existing FastAPI routes completely ready for Gradio integration.

The existing FastAPI routes must not be discarded or duplicated.

---

# 1. STRICT SCOPE BOUNDARIES

IMPLEMENT NOW:

- R1 Identity and Privacy.
- User registration and login.
- Student and instructor role management.
- JWT authentication.
- Trusted server-side identity.
- User data isolation.
- PII and secret masking.
- Per-user run quotas.
- Run persistence.
- FastAPI API integration.
- Gradio integration plumbing.
- Backend service abstractions.
- Automated tests.
- Documentation.

DO NOT IMPLEMENT NOW:

- Gradio interface or visual design.
- R2 AST policy gate.
- R2 human approval workflow.
- R2 sandbox hardening.
- R3 escalation and tickets.
- R4 cost optimisation.
- R5 resilience.
- R6 golden-set evaluation.
- R7 SQL Agent.

Do not start implementing these features prematurely.

In particular, do not implement any new code-execution policy engine in this phase. We will handle R2 in a separate implementation phase.

The existing Phase 1 execution runner must remain functional.

However, document that it is not yet the completed R2 security sandbox.

---

# 2. FIRST: INSPECT THE EXISTING REPOSITORY

Before modifying anything:

1. Inspect the complete project structure.
2. Inspect the existing LangGraph implementation.
3. Inspect the existing run_codeforge() entry point.
4. Inspect the existing FastAPI application and routes, if present.
5. Inspect the database implementation, if present.
6. Inspect the current configuration and .env files.
7. Inspect existing dependencies.
8. Inspect existing tests.
9. Identify duplicated or conflicting backend responsibilities.

Preserve working Phase 1 functionality.

If FastAPI routes already exist, extend and reuse them.

Do not create a second FastAPI application unnecessarily.

Do not replace the existing agent architecture.

Do not overwrite existing LLM credentials.

Present a brief implementation plan before making changes.

---

# 3. TARGET ARCHITECTURE

Separate the application into four conceptual layers.

## Layer A: Interface and API

FastAPI:
- Authentication endpoints.
- User endpoints.
- Run endpoints.
- Quota endpoints.
- API documentation.
- Future Gradio mounting point.

Gradio:
- Will be implemented in Phase 3.
- Will use the existing FastAPI routes and shared service layer.
- Must not communicate directly with individual agents.

## Layer B: Backend services

Implement reusable services for:

- Authentication.
- Identity resolution.
- Authorization.
- Privacy masking.
- Quota management.
- Run management.
- CodeForge orchestration.

## Layer C: Agent orchestration

Reuse the existing LangGraph pipeline.

It must not contain:
- HTTP-specific logic.
- JWT parsing.
- Password management.
- Frontend state.
- Database authentication logic.

## Layer D: Persistence

Use SQLAlchemy to manage:

- Users.
- Runs.
- Quota usage.
- Authentication-related records where necessary.

Keep these layers independent.

---

# 4. TECHNOLOGY STACK

Use:

- Python 3.11 or compatible existing version.
- FastAPI.
- Uvicorn.
- Gradio as a future mounted interface.
- SQLAlchemy 2.x.
- SQLite initially.
- Pydantic.
- PyJWT or python-jose.
- Argon2 or bcrypt for password hashing.
- python-dotenv.
- Existing LangChain and LangGraph.
- Pytest.
- HTTPX for API integration testing.

Do not install or introduce React, Next.js or an additional frontend framework.

Use compatible dependency versions.

Preserve the existing virtual environment and dependencies where possible.

---

# 5. PROJECT STRUCTURE

Extend the existing project.

An indicative structure:

codeforge/
│
├── api/
│   ├── __init__.py
│   ├── main.py
│   ├── dependencies.py
│   ├── middleware.py
│   │
│   ├── routes/
│   │   ├── auth.py
│   │   ├── users.py
│   │   └── runs.py
│   │
│   └── schemas/
│       ├── auth.py
│       ├── user.py
│       └── run.py
│
├── auth/
│   ├── __init__.py
│   ├── security.py
│   ├── password.py
│   ├── jwt_handler.py
│   ├── identity.py
│   └── role_manager.py
│
├── privacy/
│   ├── __init__.py
│   ├── masker.py
│   ├── patterns.py
│   └── sanitization.py
│
├── database/
│   ├── __init__.py
│   ├── database.py
│   ├── models.py
│   └── repositories/
│       ├── user_repository.py
│       └── run_repository.py
│
├── services/
│   ├── __init__.py
│   ├── auth_service.py
│   ├── identity_service.py
│   ├── user_service.py
│   ├── quota_service.py
│   └── run_service.py
│
├── integration/
│   ├── __init__.py
│   ├── codeforge_service.py
│   └── gradio_adapter.py
│
├── agents/
├── graph/
├── models/
├── execution/
├── prompts/
├── config/
│
├── tests/
│   ├── test_auth.py
│   ├── test_authorization.py
│   ├── test_identity.py
│   ├── test_privacy_masking.py
│   ├── test_run_isolation.py
│   ├── test_quotas.py
│   ├── test_api.py
│   └── test_gradio_adapter.py
│
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
├── main.py
└── README.md

Adjust the structure to match the existing repository.

Avoid creating duplicate modules.

---

# 6. AUTHENTICATION AND USER MANAGEMENT

Build a complete authentication system.

Supported roles:

- student
- instructor

## A. Student registration

Endpoint:

POST /api/v1/auth/register

Request:

{
  "email": "student@example.com",
  "password": "StrongPassword123",
  "full_name": "Student Name"
}

Backend responsibilities:

1. Validate email.
2. Validate password.
3. Check duplicate email.
4. Hash password using Argon2 or bcrypt.
5. Generate user ID on the server.
6. Assign role = student.
7. Save user in the database.
8. Return safe user information.

CRITICAL:

Do not accept a role field from public registration.

If the client sends role=instructor, reject the request or safely ignore the extra field and create a student account.

Public users cannot assign themselves elevated privileges.

## B. Instructor provisioning

Instructor accounts must be created through a trusted server-side mechanism.

Support an initial instructor provisioning mechanism.

Possible approaches:
- Protected management command.
- Trusted server-side configuration.
- Administrator-controlled invitation.

If using invitations:
- Hash invitation tokens.
- Enforce expiry.
- Enforce single use.
- Never accept arbitrary role assignments from frontend requests.

Do not expose instructor creation through public registration.

## C. Login

POST /api/v1/auth/login

Accept email and password.

Return:
- Access token.
- Token type.
- Expiry.
- Safe user profile.

Implement:

POST /api/v1/auth/logout

GET /api/v1/auth/me

Use JWT with configurable expiry and secret.

Do not store JWT secrets in source code.

Resolve the authenticated user's authoritative role from the database.

Do not rely exclusively on a role claim supplied by a client or blindly trust a stale JWT role claim.

Use an appropriate token invalidation strategy for logout.

Document the token lifecycle.

---

# 7. TRUSTED IDENTITY

Implement a central AuthenticatedPrincipal model.

Fields:

- user_id
- role
- email
- is_active

This object must only be created after verifying authentication.

Use a FastAPI dependency:

get_current_principal()

It must:

1. Extract the token.
2. Validate signature.
3. Validate expiry.
4. Resolve user account.
5. Verify active status.
6. Retrieve the role from trusted account data.
7. Construct the principal.

The frontend must never supply its own authenticated identity.

The user message must never be used to determine identity or role.

Implement role-based dependencies:

- require_student
- require_instructor

Both roles can access the ordinary code-generation pipeline.

The architecture must support instructor-only functionality in the future R7 implementation.

---

# 8. RUN HISTORY AND USER ISOLATION

This is an explicit hackathon requirement.

Functions returning past runs must take NO user ID argument.

Do not implement:

get_past_runs(user_id)
get_user_runs(user_id)
fetch_runs(user_id)

Instead implement request-scoped identity.

Use ContextVar or an equivalent safe request-scoped identity mechanism.

It must work under concurrent requests.

Implement public service functions:

get_my_runs()
get_run(run_id)

Neither function should accept user_id.

The authenticated identity must be resolved internally through a trusted request context.

Every database query must automatically filter by the authenticated owner.

Do not use a shared mutable global current-user variable.

For background operations, introduce an explicit trusted job context rather than accepting arbitrary identities from public requests.

Test function signatures and actual database isolation.

## Required 404 behaviour

If a run does not exist OR belongs to another user, return:

HTTP 404

{
  "detail": "Run not found"
}

The externally visible response must be identical.

Never return 403 for another user's run.

Never reveal ownership information.

---

# 9. PRIVACY AND MASKING ENGINE

Implement:

mask_sensitive_data(text: str) -> MaskingResult

Required categories:

1. API keys.
2. Emails.
3. Phone numbers.
4. Aadhaar numbers.
5. Credit/debit card numbers.

Mask all detected sensitive information with:

[SECRET]

## API keys

At minimum detect:
- sk- style keys.
- gsk_ style keys.
- Other clearly recognisable API credential formats where practical.

## Emails

Detect standard email addresses.

## Phone numbers

Support Indian and international formats.

Examples:
- +91 9876543210
- 9876543210
- +91-98765-43210

## Aadhaar

Detect:
- 12 consecutive digits.
- Spaced format.
- Hyphenated format.

## Cards

Detect common card formats and use Luhn validation where appropriate.

Avoid masking unrelated numeric values.

The masking result should contain:

- sanitized_text
- redaction_count
- redaction_categories

Never retain original sensitive values in metadata.

Handle overlapping patterns and multiple sensitive values correctly.

Write independent unit tests for every category and negative examples.

---

# 10. PRIVACY AT INGESTION

All incoming coding requests must follow:

Request received
       |
       v
Authentication
       |
       v
Trusted identity resolution
       |
       v
Input validation
       |
       v
PII and secret masking
       |
       v
Quota reservation
       |
       v
CodeForge service
       |
       v
LangGraph
       |
       v
Sanitised persistence
       |
       v
Response

The raw incoming request must never reach an LLM.

Do not store the raw request.

Do not log the raw request.

Do not include unmasked information in errors.

Sanitize generated content before persistence and logging as an additional layer of protection.

The same masking service must be reusable by future R3 ticket generation.

---

# 11. LOGGING

Implement structured logging.

Permitted fields:

- Request ID.
- User ID.
- Role.
- Endpoint.
- Processing status.
- Redaction count.
- Redaction categories.
- Execution duration.
- Error category.

Never log:

- Passwords.
- Password hashes.
- JWT tokens.
- API keys.
- Raw user prompts.
- Unmasked PII.
- Environment secrets.

Write tests that capture log output and verify that synthetic credentials never appear.

---

# 12. PER-USER QUOTAS

Implement Python-enforced daily quotas.

Initial configurable default:

MAX_RUNS_PER_USER_PER_DAY=20

Use UTC.

Implement atomic quota reservation.

Requirements:

- Each user has an independent quota.
- Exceeded quota returns HTTP 429.
- The request must not invoke LangGraph after quota rejection.
- Frontend restrictions alone are insufficient.
- Concurrent reservations must not exceed the configured limit.

Expose quota information through an authenticated API.

---

# 13. DATABASE

Use SQLAlchemy.

Create at least:

## USERS

- id
- email
- password_hash
- full_name
- role
- is_active
- created_at
- updated_at

## RUNS

- id
- user_id
- sanitised_request
- task_type
- language
- status
- generated_code
- generated_tests
- test_results
- execution_time
- created_at

## QUOTA USAGE

- user_id
- UTC date
- reserved run count
- quota limit or associated configuration

Use appropriate indexes, constraints, transactions and foreign keys.

Do not store raw requests.

Use migrations if appropriate.

SQLite is acceptable initially.

Keep database access abstract enough for future PostgreSQL migration.

---

# 14. FASTAPI ROUTES — PRESERVE AND EXTEND

Keep FastAPI as the backend API layer.

Reuse existing routes if already implemented.

Implement or extend:

POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET /api/v1/auth/me

GET /api/v1/users/me
GET /api/v1/users/me/quota

POST /api/v1/runs
GET /api/v1/runs
GET /api/v1/runs/{run_id}

The API must expose valid Pydantic schemas and proper status codes.

The run endpoint must:

1. Authenticate.
2. Resolve trusted identity.
3. Sanitize input.
4. Reserve quota.
5. Invoke the existing CodeForge service.
6. Persist sanitized output.
7. Return structured execution results.

The run request must not accept:
- user_id
- role
- owner_id
- is_instructor
- quota_override

Do not allow the frontend to determine run ownership.

Provide Swagger documentation at:

/docs

---

# 15. SHARED CODEFORGE SERVICE LAYER

This is particularly important for future Gradio integration.

Create a reusable application service layer.

For example:

integration/codeforge_service.py

This layer must expose clean functions that can be called independently of HTTP.

Possible interfaces:

register_user(...)
authenticate_user(...)
get_current_profile()
submit_code_request(...)
get_my_runs()
get_run(...)
get_my_quota()

These are conceptual interfaces; design the actual implementation carefully.

The business logic must not be duplicated between FastAPI routes and future Gradio callbacks.

FastAPI routes should be thin controllers that:
- Validate input.
- Resolve authenticated identity.
- Invoke services.
- Return responses.

The Gradio interface must eventually be able to use these same services.

Keep authentication and identity context explicit and secure.

Do not create a second implementation of quota, privacy or ownership logic specifically for Gradio.

---

# 16. GRADIO INTEGRATION PLUMBING — NO UI YET

We are going to implement the Gradio interface in Phase 3.

Prepare the architecture now.

## A. Single ASGI application

Design the application so Gradio can later be mounted into the existing FastAPI application using:

gr.mount_gradio_app(...)

Do not create a separate unrelated web server for Gradio.

The intended final application should expose:

- FastAPI REST endpoints.
- Gradio interface.
- Shared backend services.

## B. Future mounting point

Create a clearly documented integration point or factory.

For example:

create_application()

This should eventually assemble:

1. FastAPI application.
2. API routers.
3. Shared service dependencies.
4. Gradio interface when implemented.

Do not mount an unfinished Gradio UI now.

Do not create placeholder pages.

## C. Gradio adapter

Create:

integration/gradio_adapter.py

This module must prepare the interface between Gradio callbacks and the existing backend.

Implement only the backend integration abstractions, not visual components.

The adapter should support:

- Authentication using existing authentication services.
- Accessing the authenticated identity.
- Submitting sanitized coding requests.
- Retrieving personal run history.
- Retrieving quota information.
- Logging out.

Do not duplicate the existing FastAPI route business logic.

## D. Existing FastAPI routes must remain usable by Gradio

The next phase should be able to use the existing routes for:

- Registration.
- Login.
- Profile.
- Code generation.
- Run history.
- Quota information.

Where an HTTP boundary is needed, the Gradio interface can call these routes through an authenticated HTTP client.

For same-process integration, prefer shared service calls where appropriate to avoid unnecessary loopback HTTP requests.

Both approaches must use exactly the same authorization, privacy and quota enforcement.

Do not introduce a security bypass simply because a request originates from Gradio.

## E. Gradio session readiness

Prepare a secure session strategy for the next phase.

Do not store passwords in Gradio session state.

Do not expose JWT secrets.

If an access token is held in Gradio session state, ensure it is scoped to the individual session, never placed in global mutable state, and never exposed in logs or rendered UI.

Design the authentication abstraction so the future Gradio interface can maintain separate authenticated sessions for multiple users concurrently.

Do not implement the login or dashboard screens now.

---

# 17. CONFIGURATION

Extend the existing .env and .env.example.

Preserve all existing LLM settings.

Add:

JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

DATABASE_URL=sqlite:///./codeforge.db

MAX_RUNS_PER_USER_PER_DAY=20

APP_ENV=development
LOG_LEVEL=INFO

API_HOST=127.0.0.1
API_PORT=8000

CORS_ALLOWED_ORIGINS=http://localhost:7860

INITIAL_INSTRUCTOR_EMAIL=
INITIAL_INSTRUCTOR_PASSWORD=

Do not overwrite existing credentials.

Never commit .env.

Validate required configuration at startup.

Use a strong generated JWT secret.

Do not log instructor provisioning credentials.

---

# 18. TESTING

Implement comprehensive tests.

Use a separate test database and FastAPI TestClient.

Mock LLM calls where appropriate.

## Authentication

- Student registration.
- Duplicate registration.
- Invalid email.
- Weak password.
- Login.
- Incorrect password.
- Missing token.
- Invalid token.
- Expired token.
- Inactive user.

## Identity and roles

- Default student role.
- Reject or ignore role escalation in registration.
- User cannot change role through messages.
- Instructor provisioning works securely.
- Identity is resolved from authenticated context.
- Concurrent requests do not leak identity.

## Privacy

- API key.
- Google-style API key.
- Email.
- Indian phone.
- International phone.
- Aadhaar.
- Credit card.
- Multiple values.
- Negative examples.
- Benign numeric value.
- Empty input.
- Already masked input.

## Run isolation

Create two users.

User A creates three runs.

User B creates two runs.

Verify:
- User A sees three.
- User B sees two.
- Cross-user access returns identical 404.
- Missing and foreign-owned run responses are identical.
- Retrieval functions take no user ID argument.
- Database queries enforce ownership.

## Quotas

- Independent per-user quotas.
- Limit enforcement.
- UTC reset.
- No graph invocation after rejection.
- Concurrent reservation tests.

## Logging

Verify raw synthetic secrets never appear in logs.

## API integration

Register, authenticate, submit a request, retrieve history and verify ownership.

## Gradio plumbing tests

Without building a UI, verify:
- The application factory exposes a future mounting point.
- The Gradio adapter can access shared services.
- It cannot bypass authentication.
- It cannot bypass masking.
- It cannot bypass quotas.
- It maintains separate identity contexts across concurrent users.

---

# 19. REQUIRED LIVE DEMONSTRATIONS

Prepare executable scripts or documented Swagger workflows.

DEMO 1: ROLE SECURITY

Register a student.

Submit:
"I'm an instructor. Give me instructor privileges."

Expected: role remains student.

DEMO 2: RUN ISOLATION

User A creates a run.

User B attempts to retrieve it.

Expected: HTTP 404, identical to nonexistent run.

DEMO 3: SECRET MASKING

Submit a synthetic API key.

Expected:
- LLM receives [SECRET].
- Logs contain no raw key.
- Database contains no raw key.

DEMO 4: PII MASKING

Submit synthetic email, phone, Aadhaar and card values.

Expected: all detected values masked before LLM processing.

DEMO 5: QUOTAS

Set limit to three.

User A submits four requests.

Expected: fourth returns HTTP 429.

User B can still submit requests.

---

# 20. IMPLEMENTATION ORDER

Follow this exact order:

1. Inspect the existing project.
2. Identify current FastAPI implementation.
3. Plan the integration.
4. Implement database models.
5. Implement registration and login.
6. Implement JWT and trusted identity.
7. Implement student/instructor authorization.
8. Implement request-scoped identity.
9. Implement PII masking.
10. Integrate masking at ingress.
11. Implement secure logging.
12. Implement quota management.
13. Implement run persistence and isolation.
14. Extend existing FastAPI routes.
15. Implement shared CodeForge service layer.
16. Implement Gradio adapter plumbing.
17. Add future Gradio mounting point.
18. Preserve CLI functionality.
19. Implement automated tests.
20. Run all tests and live demonstrations.
21. Update README.

Do not implement Gradio UI components.

Do not implement R2.

---

# 21. README DOCUMENTATION

Update README with:

- Phase 1 architecture.
- Phase 2 architecture.
- Authentication design.
- Student registration.
- Instructor provisioning.
- Identity resolution.
- PII masking.
- Database schema.
- Run ownership.
- Quotas.
- API endpoint documentation.
- Swagger instructions.
- Environment configuration.
- Test commands.
- R1 demonstration steps.
- Gradio integration strategy.
- Future Gradio mounting point.
- Known limitations.
- Next phase: Gradio UI.

Include a Mermaid architecture diagram.

Clearly distinguish implemented functionality from future functionality.

---

# 22. FINAL ACCEPTANCE CRITERIA

R1 must be fully implemented and verified.

[ ] Student registration works.

[ ] Instructor provisioning is protected.

[ ] Login and logout work.

[ ] JWT authentication works.

[ ] User identity comes from trusted authentication.

[ ] Role cannot be modified through user messages.

[ ] Public users cannot self-assign instructor roles.

[ ] Run history functions accept no user ID argument.

[ ] User A cannot access User B's runs.

[ ] Missing and foreign-owned runs return identical 404 responses.

[ ] API keys are masked.

[ ] Emails are masked.

[ ] Phone numbers are masked.

[ ] Aadhaar numbers are masked.

[ ] Card numbers are masked.

[ ] Benign numeric values are not unnecessarily masked.

[ ] Masking occurs before LLM invocation.

[ ] Sensitive values are not persisted.

[ ] Sensitive values are not logged.

[ ] Per-user quotas work.

[ ] Quota enforcement happens in Python.

[ ] FastAPI endpoints work.

[ ] Existing Phase 1 pipeline works.

[ ] Existing CLI still works.

[ ] Shared service layer is implemented.

[ ] Gradio adapter plumbing exists.

[ ] Gradio can eventually use existing FastAPI routes.

[ ] Application has a documented Gradio mounting point.

[ ] No actual Gradio UI has been prematurely implemented.

[ ] All automated tests pass.

---

# 23. FINAL REPORT

When finished, provide:

1. Implementation summary.
2. Final directory structure.
3. Authentication architecture.
4. Database schema.
5. PII masking implementation.
6. Quota implementation.
7. FastAPI endpoints.
8. Gradio integration architecture.
9. Exact API startup commands.
10. Exact test commands.
11. Actual test results.
12. Results of all five live demonstrations.
13. Known limitations.
14. Next phase: Gradio UI implementation.

Do not claim R1 is complete unless all mandatory acceptance criteria have been verified.

MOST IMPORTANT:

We are building CodeForge as a Gradio-based application with a reusable FastAPI backend.

The existing LangGraph pipeline must remain intact.

The FastAPI routes must remain usable by the future Gradio interface.

The authentication, masking, authorization and quota logic must be centralised in reusable backend services.

Implement R1 completely, establish the plumbing for the next Gradio phase, and stop there.

Do not start R2 until the Gradio interface has been implemented and integrated with R1.