"""FastAPI application factory with the Gradio workspace mounted at /ui.

Start the integrated application with:

    python -m codeforge.api.main

Swagger documentation is served at /docs. The Gradio UI is at /ui.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from codeforge.api.middleware import RequestLoggingMiddleware
from codeforge.api.routes import auth as auth_routes
from codeforge.api.routes import approvals as approval_routes
from codeforge.api.routes import runs as runs_routes
from codeforge.api.routes import sql as sql_routes
from codeforge.api.routes import support as support_routes
from codeforge.api.routes import users as users_routes
from codeforge.auth.jwt_handler import _require_secret
from codeforge.config.settings import get_settings
from codeforge.database.database import init_db

from codeforge.exceptions import (
    AuthenticationError,
    AuthorizationError,
    InvitationError,
    QuotaExceededError,
    RegistrationError,
    RunNotFoundError,
    ApprovalConflictError,
    ApprovalNotFoundError,
    FeedbackConflictError,
    SqlAgentDisabledError,
    SqlTicketNotFoundError,
)
from codeforge.services.auth_service import bootstrap_initial_instructor

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


def create_application(include_gradio: bool = False) -> FastAPI:
    """Assemble the single ASGI application.

    This is the documented GRADIO MOUNTING POINT.

    When ``include_gradio`` is True (the production entry point), the Gradio
    workspace is mounted into this same FastAPI app:

        import gradio as gr
        from codeforge.ui.app import build_interface

        interface = build_interface()   # uses integration.gradio_adapter
        app = gr.mount_gradio_app(app, interface, path="/ui")

    No separate web server is created for Gradio. FastAPI REST endpoints
    (``/api/v1``, ``/docs``) and the Gradio UI (``/ui``) share one process and
    the same backend services.

    Tests call ``create_application()`` without Gradio so the suite stays fast
    and does not require a browser. Production uses
    ``create_application(include_gradio=True)`` via ``python -m codeforge.api.main``.
    """
    settings = get_settings()

    # Fail fast on incomplete security configuration.
    _require_secret(settings)

    init_db()
    bootstrap_initial_instructor()

    app = FastAPI(
        title="CodeForge API",
        version="0.2.0",
        description=(
            "Natural Language to Code platform — R1 through R2, R6 and the R7 SQL agent. "
            "REST API at /api/v1, Gradio workspace at /ui, Swagger at /docs."
        ),
        docs_url="/docs",
    )

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_routes.router, prefix=API_PREFIX)
    app.include_router(users_routes.router, prefix=API_PREFIX)
    app.include_router(runs_routes.router, prefix=API_PREFIX)
    app.include_router(approval_routes.router, prefix=API_PREFIX)
    app.include_router(sql_routes.router, prefix=API_PREFIX)
    app.include_router(support_routes.router, prefix=API_PREFIX)

    _register_exception_handlers(app)

    if include_gradio:
        import gradio as gr

        from codeforge.ui.app import build_interface

        @app.get("/", include_in_schema=False)
        def root_redirect() -> RedirectResponse:
            """Send browsers to the Gradio workspace; API docs remain at /docs."""
            return RedirectResponse(url="/ui")

        from codeforge.ui.theme import THEME_CSS, build_theme

        interface = build_interface()
        app = gr.mount_gradio_app(
            app,
            interface,
            path="/ui",
            theme=build_theme(),
            css=THEME_CSS,
            show_error=True,
        )

    logger.info("application_created api_prefix=%s include_gradio=%s", API_PREFIX, include_gradio)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    """Map domain errors to proper HTTP responses (no sensitive details)."""

    def _handler(status_code: int):
        async def handle(request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(status_code=status_code, content={"detail": str(exc)})

        return handle

    app.add_exception_handler(AuthenticationError, _handler(status.HTTP_401_UNAUTHORIZED))
    app.add_exception_handler(AuthorizationError, _handler(status.HTTP_403_FORBIDDEN))
    app.add_exception_handler(RegistrationError, _handler(status.HTTP_400_BAD_REQUEST))
    app.add_exception_handler(InvitationError, _handler(status.HTTP_400_BAD_REQUEST))
    app.add_exception_handler(QuotaExceededError, _handler(status.HTTP_429_TOO_MANY_REQUESTS))
    app.add_exception_handler(ApprovalConflictError, _handler(status.HTTP_409_CONFLICT))
    app.add_exception_handler(FeedbackConflictError, _handler(status.HTTP_409_CONFLICT))
    app.add_exception_handler(ValueError, _handler(422))

    async def handle_run_not_found(request: Request, exc: RunNotFoundError) -> JSONResponse:
        # Identical body for missing and foreign-owned runs. Never 403.
        return JSONResponse(status_code=404, content={"detail": "Run not found"})

    app.add_exception_handler(RunNotFoundError, handle_run_not_found)

    async def handle_approval_not_found(request: Request, exc: ApprovalNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Approval request not found"})

    app.add_exception_handler(ApprovalNotFoundError, handle_approval_not_found)

    async def handle_ticket_not_found(request: Request, exc: SqlTicketNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Ticket not found"})

    app.add_exception_handler(SqlTicketNotFoundError, handle_ticket_not_found)
    app.add_exception_handler(SqlAgentDisabledError, _handler(status.HTTP_503_SERVICE_UNAVAILABLE))


def main() -> None:
    """Run the API server (python -m codeforge.api.main)."""
    import uvicorn

    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run(
        "codeforge.api.main:create_ui_application",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
    )


def create_ui_application() -> FastAPI:
    """Production factory: FastAPI + Gradio on one ASGI server."""
    return create_application(include_gradio=True)


if __name__ == "__main__":
    main()
