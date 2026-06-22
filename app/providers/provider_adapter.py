from abc import ABC, abstractmethod


class ProviderAdapter(ABC):
    """
    Defines the interface for all LLM provider adapters.

    Provider adapters are responsible only for communicating with an
    inference provider and returning the provider's raw response.

    They are NOT responsible for:

    - Authorization
    - Policy evaluation
    - Risk assessment
    - Tool execution
    - ToolInvocation parsing
    """

    @abstractmethod
    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        """
        Send a request to the configured provider and return
        the raw provider response.
        """
        ...