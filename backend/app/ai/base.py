from abc import ABC, abstractmethod


class AIError(Exception):
    """The AI provider could not answer. `retry` says whether trying again later could help."""

    def __init__(self, message: str, retry: bool = True):
        super().__init__(message)
        self.retry = retry


class AIProvider(ABC):
    """Anything that can answer a prompt with JSON in a given shape. Gemini today; others fit the same interface."""

    name: str = ""

    @abstractmethod
    def generate_json(self, system: str, user: str, schema: dict) -> str:
        """Return the model's answer as JSON text. Raises AIError."""
