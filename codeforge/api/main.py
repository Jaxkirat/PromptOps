"""FastAPI application factory with the future Gradio mounting point.

Start the API with either:

    uvicorn codeforge.api.main:create_application --factory

or:

    python -m codeforge.api.main

Swagger documentation is served at /docs.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from codeforge.api.middleware import RequestLoggingMiddleware
from codeforge.api.routes import auth as auth_routes
from codeforge.api.routes import runs as runs_routes
from codeforge.api.routes import users as users_routes
from codeforge.auth.jwt_handler import _require_secret
from codeforge.config.settings import get_settings
from codeforge.database.database import init_db
from codeforge.exceptions import (
    AuthenticationError,
    AuthorizationError,
    QuotaExceededError,
    RegistrationError,
    RunNotFoundError,
)
from codeforge.services.auth_service import bootstrap_initial_instructor

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


def create_application(include_gradio: bool = False) -> FastAPI:
    """Assemble the single ASGI application.

    This is the documented GRADIO MOUNTING POINT for Phase 3. When the Gradio
    interface is implemented, it will be mounted into this same FastAPI app:

        import gradio as gr
        from codeforge.integration.gradio_ui import build_interface  # Phase 3

        interface = build_interface()   # uses integration.gradio_adapter
        app = gr.mount_gradio_app(app, interface, path="/ui")

    No separate web server is created for Gradio; FastAPI REST endpoints,
    the Gradio UI and the shared backend services live in ONE application.
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
            "Natural Language to Code platform — Phase 2 (R1: identity, privacy, "
            "quotas, run history). Gradio UI arrives in Phase 3."
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

    _register_exception_handlers(app)

    if include_gradio:
        # Phase 3 will replace this guard with the actual gr.mount_gradio_app call.
        raise NotImplementedError(
            "The Gradio interface is implemented in Phase 3. "
            "Mount it here via gr.mount_gradio_app(app, interface, path='/ui')."
        )

    logger.info("application_created api_prefix=%s", API_PREFIX)
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
    app.add_exception_handler(QuotaExceededError, _handler(status.HTTP_429_TOO_MANY_REQUESTS))
    app.add_exception_handler(ValueError, _handler(422))

    async def handle_run_not_found(request: Request, exc: RunNotFoundError) -> JSONResponse:
        # Identical body for missing and foreign-owned runs. Never 403.
        return JSONResponse(status_code=404, content={"detail": "Run not found"})

    app.add_exception_handler(RunNotFoundError, handle_run_not_found)


def main() -> None:
    """Run the API server (python -m codeforge.api.main)."""
    import uvicorn

    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run(
        "codeforge.api.main:create_application",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
    )


if __name__ == "__main__":
    main()
