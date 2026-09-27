"""Exception hierarchy for llm_router. See ARCHITECTURE.md sec 7."""

from __future__ import annotations

import re

_API_KEY_RE = re.compile(r"sk-[a-zA-Z]{2,4}-[A-Za-z0-9_\-]{10,}")


def redact_api_key(message: str) -> str:
    return _API_KEY_RE.sub("sk-***-redacted", message)


class LLMError(Exception):
    """Base for every llm_router error."""


class ProviderError(LLMError):
    def __init__(
        self,
        provider: str,
        message: str,
        *,
        status: int | None = None,
        retriable: bool = False,
    ) -> None:
        self.provider = provider
        self.status = status
        self.retriable = retriable
        super().__init__(f"[{provider}] {redact_api_key(message)}")


class BudgetExceeded(LLMError):
    def __init__(self, use_case: str, cost_usd: float, threshold: float) -> None:
        self.use_case = use_case
        self.cost_usd = cost_usd
        self.threshold = threshold
        super().__init__(
            f"use_case={use_case} estimated_cost=${cost_usd:.4f} > cap=${threshold:.4f}"
        )


class SchemaValidationError(LLMError):
    def __init__(self, provider: str, raw_output: object) -> None:
        self.provider = provider
        self.raw_output = raw_output
        rendered = repr(raw_output)
        if len(rendered) > 200:
            rendered = rendered[:200] + "..."
        super().__init__(f"[{provider}] tool_input not parseable: {rendered}")


class ConfigError(LLMError):
    """Raised at set_routing_config() time for malformed yaml or missing references."""


class RoutingNotConfigured(LLMError):
    """Raised when call_tool() is called before set_routing_config()."""
