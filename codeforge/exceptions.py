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
