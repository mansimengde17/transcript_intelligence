"""Provider abstraction with budget enforcement and an optional OpenAI Responses adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from .observability import CostEstimator


@dataclass(frozen=True)
class BudgetPolicy:
    max_input_characters: int = 40_000
    max_output_tokens: int = 800
    max_cost_usd: float = 0.02


@dataclass
class ModelResult:
    data: dict[str, Any]
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


class ModelGateway(Protocol):
    def generate_json(self, system_prompt: str, user_prompt: str, policy: BudgetPolicy) -> ModelResult:
        ...


class BudgetExceeded(RuntimeError):
    pass


class DeterministicGateway:
    """Offline gateway used in tests and fallbacks."""

    def generate_json(self, system_prompt: str, user_prompt: str, policy: BudgetPolicy) -> ModelResult:
        if len(user_prompt) > policy.max_input_characters:
            raise BudgetExceeded("Input exceeds deterministic budget policy")
        return ModelResult(
            data={"mode": "deterministic", "summary": user_prompt[:240]},
            model="deterministic",
            input_tokens=max(1, len(user_prompt) // 4),
            output_tokens=min(80, policy.max_output_tokens),
            estimated_cost_usd=0.0,
        )


class OpenAIResponsesGateway:
    """Optional structured-output adapter. Credentials come from the SDK environment."""

    def __init__(self, model: str, prices_per_million: tuple[float, float]):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install requirements-agentic.txt to use the OpenAI adapter") from exc
        self.client = OpenAI()
        self.model = model
        self.costs = CostEstimator({model: prices_per_million})

    def generate_json(self, system_prompt: str, user_prompt: str, policy: BudgetPolicy) -> ModelResult:
        if len(user_prompt) > policy.max_input_characters:
            raise BudgetExceeded("Input exceeds model budget policy")
        response = self.client.responses.create(
            model=self.model,
            instructions=system_prompt,
            input=user_prompt,
            max_output_tokens=policy.max_output_tokens,
            text={"format": {"type": "json_object"}},
        )
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", max(1, len(user_prompt) // 4)))
        output_tokens = int(getattr(usage, "output_tokens", policy.max_output_tokens))
        cost = self.costs.estimate(self.model, input_tokens, output_tokens)
        if cost > policy.max_cost_usd:
            raise BudgetExceeded(f"Estimated cost ${cost:.6f} exceeds ${policy.max_cost_usd:.6f}")
        return ModelResult(
            data=json.loads(response.output_text),
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
        )
