"""Custom exception types used across the CodeForge pipeline."""


class CodeForgeError(Exception):
    """Base class for all CodeForge-specific errors."""


class ConfigurationError(CodeForgeError):
    """Raised when required configuration (e.g. LLM credentials) is missing or invalid."""


class AgentExecutionError(CodeForgeError):
    """Raised when an agent fails to produce a valid structured output."""

    def __init__(self, agent_name: str, message: str) -> None:
        self.agent_name = agent_name
        super().__init__(f"[{agent_name}] {message}")


# --- R1: identity, privacy and quota errors --------------------------------


class AuthenticationError(CodeForgeError):
    """Raised when credentials or tokens cannot be verified."""


class AuthorizationError(CodeForgeError):
    """Raised when an authenticated principal lacks the required role."""


class RegistrationError(CodeForgeError):
    """Raised when registration input is invalid (duplicate email, weak password...)."""


class QuotaExceededError(CodeForgeError):
    """Raised when a user's daily run quota is exhausted."""


class RunNotFoundError(CodeForgeError):
    """Raised when a run does not exist or is not owned by the caller.

    Deliberately identical for both cases so ownership is never revealed.
    """

    def __init__(self) -> None:
        super().__init__("Run not found")


class InvitationError(CodeForgeError):
    """Raised when an instructor invitation is invalid, expired or already used."""


class FeedbackConflictError(CodeForgeError):
    """This user already recorded feedback for the run."""

    def __init__(self) -> None:
        super().__init__("Feedback already exists for this run")


class ApprovalNotFoundError(CodeForgeError):
    """Missing approval, or one the caller is not allowed to see. Same response."""

    def __init__(self) -> None:
        super().__init__("Approval request not found")


class SqlAgentDisabledError(CodeForgeError):
    """The SQL agent is turned off or its parser/dialect is not available."""

    def __init__(self, message: str = "The SQL agent is disabled.") -> None:
        super().__init__(message)


class SqlTicketNotFoundError(CodeForgeError):
    """Missing ticket, or one this instructor is not assigned. Same response."""

    def __init__(self) -> None:
        super().__init__("Ticket not found")


class ApprovalConflictError(CodeForgeError):
    """The approval was already decided, expired, or lost a race."""

    def __init__(self, message: str = "Approval request is no longer pending.") -> None:
        super().__init__(message)
