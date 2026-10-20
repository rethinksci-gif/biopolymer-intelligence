"""DeepSeek client: model availability check, JSON mode + pydantic validation, retries with backoff,
a per-run call budget and token accounting. The API key is read from the environment and never logged."""
from __future__ import annotations

import json
import os
import time
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .config import llm_config, max_calls

T = TypeVar("T", bound=BaseModel)


class BudgetExceeded(RuntimeError):
    pass


class LLMError(RuntimeError):
    pass


def have_key() -> bool:
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


class LLM:
    def __init__(self, client=None, budget: int | None = None):
        self.budget = budget if budget is not None else max_calls()
        self.calls = 0
        self.by_model: dict[str, dict] = {}
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            key = os.environ.get("DEEPSEEK_API_KEY")
            if not key:
                raise LLMError("DEEPSEEK_API_KEY is not set")
            cfg = llm_config()
            self._client = OpenAI(api_key=key, base_url=cfg["base_url"], timeout=cfg["timeout_seconds"], max_retries=0)
        return self._client

    def check_models(self, *names: str) -> list[str]:
        """Fail clearly if a configured model is not offered by the API (names change; no silent fallback)."""
        available = sorted(m.id for m in self.client.models.list().data)
        missing = [n for n in names if n not in available]
        if missing:
            raise LLMError(f"Configured model(s) {missing} not available. The API lists: {available}. "
                           "Update config/llm.yaml or DEEPSEEK_*_MODEL.")
        return available

    @property
    def usage(self) -> dict:
        return {"prompt_tokens": sum(v["prompt_tokens"] for v in self.by_model.values()),
                "completion_tokens": sum(v["completion_tokens"] for v in self.by_model.values())}

    def cost_usd(self) -> float | None:
        price = llm_config().get("price_per_mtok") or {}
        if price.get("input") is None or price.get("output") is None:
            return None
        u = self.usage
        return round((u["prompt_tokens"] * price["input"] + u["completion_tokens"] * price["output"]) / 1e6, 4)

    def json_call(self, model: str, system: str, user: str, schema: type[T], max_tokens: int = 3000) -> T:
        cfg = llm_config()
        last: Exception | None = None
        for attempt in range(cfg["max_retries"] + 1):
            if self.calls >= self.budget:
                raise BudgetExceeded(f"LLM call budget of {self.budget} reached")
            self.calls += 1
            stats = self.by_model.setdefault(model, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0})
            stats["calls"] += 1
            try:
                resp = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    response_format={"type": "json_object"},
                    temperature=cfg["temperature"],
                    max_tokens=max_tokens + cfg["reasoning_headroom"],
                )
            except Exception as exc:  # transport/API errors: back off and retry within the budget
                last = exc
                time.sleep(cfg["backoff_seconds"] * 2 ** attempt)
                continue
            if resp.usage:
                stats["prompt_tokens"] += resp.usage.prompt_tokens
                stats["completion_tokens"] += resp.usage.completion_tokens
            try:
                return schema.model_validate(json.loads(resp.choices[0].message.content or ""))
            except (json.JSONDecodeError, ValidationError) as exc:
                last = exc
        raise LLMError(f"no valid model output after retries: {type(last).__name__}: {str(last)[:300]}")
