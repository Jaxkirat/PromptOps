"""Authentication, trusted identity and role management."""

from codeforge.auth.identity import (
    AuthenticatedPrincipal,
    current_principal,
    principal_context,
)

__all__ = ["AuthenticatedPrincipal", "current_principal", "principal_context"]
