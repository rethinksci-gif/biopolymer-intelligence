from __future__ import annotations

import os
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PROMPTS = ROOT / "prompts"
SCHEMAS = ROOT / "schemas"
CACHE = DATA / "cache"


@cache
def config() -> dict:
    return yaml.safe_load((ROOT / "config" / "site.yaml").read_text())


@cache
def llm_config() -> dict:
    return yaml.safe_load((ROOT / "config" / "llm.yaml").read_text())


def load(name: str):
    return yaml.safe_load((DATA / f"{name}.yaml").read_text())


def triage_model() -> str:
    return os.environ.get("DEEPSEEK_TRIAGE_MODEL") or llm_config()["triage_model"]


def draft_model() -> str:
    return os.environ.get("DEEPSEEK_DRAFT_MODEL") or llm_config().get("draft_model") or triage_model()


def max_calls() -> int:
    return int(os.environ.get("MAX_LLM_CALLS_PER_RUN") or llm_config()["max_calls_per_run"])
