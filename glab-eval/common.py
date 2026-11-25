"""Shared helpers for the glab evaluation harness."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent

# Short flags whose long form is unambiguous across the commands in tasks.jsonl.
SHORT_ALIASES: dict[str, str] = {
    "-R": "--repo",
    "-a": "--assignee",
    "-A": "--all",
    "-b": "--branch",
    "-g": "--group",
    "-l": "--label",
    "-m": "--milestone",
    "-M": "--merged",
    "-P": "--per-page",
}

THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
FUNCTION_RE = re.compile(r"<function=([^>]+)>")
PARAMETER_RE = re.compile(r"<parameter=([^>]+)>(.*?)</parameter>", re.DOTALL)


def load_config() -> dict[str, Any]:
    # The default is the frozen baseline config. GLAB_EVAL_CONFIG lets the
    # separate lora-eval suite reuse the same harness against a LoRA endpoint.
    # The endpoint can be pointed elsewhere without editing the frozen file:
    # GLAB_EVAL_ENDPOINT, GLAB_EVAL_MODEL and GLAB_EVAL_API_KEY override the
    # three connection fields.
    path = Path(os.environ.get("GLAB_EVAL_CONFIG", ROOT / "config.yaml"))
    with path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    for key, env_name in (
        ("base_url", "GLAB_EVAL_ENDPOINT"),
        ("model_id", "GLAB_EVAL_MODEL"),
        ("api_key", "GLAB_EVAL_API_KEY"),
    ):
        value = os.environ.get(env_name)
        if value:
            config["endpoint"][key] = value
    return config


def load_sources() -> dict[str, Any]:
    with (ROOT / "docs" / "sources.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def tasks_path() -> Path:
    """Resolve the task file: GLAB_EVAL_TASKS wins, otherwise tasks.jsonl."""
    value = os.environ.get("GLAB_EVAL_TASKS")
    if not value:
        return ROOT / "tasks.jsonl"
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_tasks(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or tasks_path()
    tasks = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            task = json.loads(line)
            task["_line"] = line_number
            tasks.append(task)
    return tasks


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_inputs(config: dict[str, Any]) -> list[Path]:
    paths = [
        ROOT / "config.yaml",
        tasks_path(),
        ROOT / "common.py",
        ROOT / "validate_tasks.py",
        ROOT / "run_eval.py",
        ROOT / "score.py",
        ROOT / "docs" / "sources.json",
    ]
    paths.extend(ROOT / "docs" / item["file"] for item in load_sources()["sources"])
    return sorted(set(paths))


def canonical_hash(config: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for path in canonical_inputs(config):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_tool(config: dict[str, Any]) -> dict[str, Any]:
    spec = config["tool"]
    return {
        "type": "function",
        "function": {
            "name": spec["name"],
            "description": spec["description"],
            "parameters": {
                "type": "object",
                "properties": {
                    name: {"type": field["type"], "description": field["description"]}
                    for name, field in spec["parameters"].items()
                },
                "required": list(spec["parameters"]),
                "additionalProperties": False,
            },
        },
    }


def tool_schema_sha256(config: dict[str, Any]) -> str:
    return sha256_bytes(
        json.dumps(build_tool(config), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )


def tokenize(command: str | None) -> list[str]:
    if not command:
        return []
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    normalized: list[str] = []
    for token in tokens:
        if token.startswith("--") and "=" in token:
            flag, value = token.split("=", 1)
            normalized.extend([flag, value])
        else:
            normalized.append(SHORT_ALIASES.get(token, token))
    return normalized


def normalize_command(command: str | None) -> str:
    return " ".join(tokenize(command))


def parse_model_output(response: dict[str, Any]) -> dict[str, Any]:
    """Extract a command from an OpenAI-style response message."""
    message = response.get("message") or {}
    tool_calls = message.get("tool_calls") or []
    raw_text = message.get("content") or ""
    reasoning = message.get("reasoning") or ""
    visible_text = THINK_RE.sub("", raw_text).strip()
    result: dict[str, Any] = {
        "command": None,
        "output_format": "none",
        "parse_error": None,
        "reasoning_leak": bool(re.search(r"<think>", raw_text or "")),
        "visible_text": visible_text,
        "reasoning": reasoning,
    }

    if tool_calls:
        function = (tool_calls[0].get("function") or {})
        arguments = function.get("arguments")
        parsed: Any = arguments
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError:
                parsed = None
                result["parse_error"] = "invalid_json_args"
        if isinstance(parsed, dict):
            if isinstance(parsed.get("command"), str):
                result["command"] = parsed["command"]
            elif len(parsed) == 1 and isinstance(next(iter(parsed.values())), str):
                result["command"] = next(iter(parsed.values()))
            else:
                result["parse_error"] = result["parse_error"] or "invalid_json_args"
        if result["command"] is None and result["parse_error"] is None:
            result["parse_error"] = "invalid_json_args"
        result["output_format"] = "api_json"
        return result

    if "<tool_call>" in visible_text:
        function_match = FUNCTION_RE.search(visible_text)
        parameter_matches = PARAMETER_RE.findall(visible_text)
        if function_match and parameter_matches:
            values = {name.strip(): value.strip() for name, value in parameter_matches}
            result["command"] = values.get("command", parameter_matches[0][1].strip())
            result["output_format"] = "xml"
            return result
        result["parse_error"] = "invalid_xml"
        result["output_format"] = "xml"
        return result

    if visible_text:
        result["output_format"] = "text"
        result["command"] = visible_text
        result["parse_error"] = "no_tool_call"
        return result

    result["parse_error"] = "no_tool_call"
    return result
