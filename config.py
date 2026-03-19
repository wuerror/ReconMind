import os
from typing import Any, Dict

import yaml


DEFAULT_CONFIG: Dict[str, Dict[str, Any]] = {
    "llm": {
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.3-codex",
        "api_mode": "auto",  # auto | responses | chat
        "stream": True,
        "reasoning_effort": "high",  # low | medium | high
    },
    "tools": {},
    "api_keys": {},
    "credentials": {},
    "active": {
        "proxy": "",
        "gogo_threads": 0,
    },
    "agent": {
        "max_iterations": 30,
        "timeout": 60,
        "output_dir": "./output",
        "llm_retries": 4,
        "llm_timeout": 120,
    },
}


def _merge_defaults(config: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {
        "llm": {**DEFAULT_CONFIG["llm"], **(config.get("llm") or {})},
        "tools": {**DEFAULT_CONFIG["tools"], **(config.get("tools") or {})},
        "api_keys": {**DEFAULT_CONFIG["api_keys"], **(config.get("api_keys") or {})},
        "credentials": {
            **DEFAULT_CONFIG["credentials"],
            **(config.get("credentials") or {}),
        },
        "active": {**DEFAULT_CONFIG["active"], **(config.get("active") or {})},
        "agent": {**DEFAULT_CONFIG["agent"], **(config.get("agent") or {})},
    }
    return merged


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    """Load config from YAML and apply OPENAI_* environment overrides."""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    config = _merge_defaults(raw)

    if os.getenv("OPENAI_API_KEY"):
        config["llm"]["api_key"] = os.getenv("OPENAI_API_KEY")
    if os.getenv("OPENAI_BASE_URL"):
        config["llm"]["base_url"] = os.getenv("OPENAI_BASE_URL")
    if os.getenv("OPENAI_MODEL"):
        config["llm"]["model"] = os.getenv("OPENAI_MODEL")
    if os.getenv("OPENAI_API_MODE"):
        config["llm"]["api_mode"] = os.getenv("OPENAI_API_MODE")
    if os.getenv("OPENAI_STREAM"):
        config["llm"]["stream"] = os.getenv("OPENAI_STREAM")
    if os.getenv("OPENAI_REASONING_EFFORT"):
        config["llm"]["reasoning_effort"] = os.getenv("OPENAI_REASONING_EFFORT")

    return config
