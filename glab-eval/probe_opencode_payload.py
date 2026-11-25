"""Replay the frozen OpenCode request shape against a configured endpoint.

Shell-shape training renders with the `shell` tool only; this probe sends the
FULL frozen tool list (14 tools from the live capture) plus the production
system prompt so a human can review which tool the served adapter picks for
real-world prompts. It is a manual review artifact, not a scored suite.

Usage (from glab-eval/):
    GLAB_EVAL_CONFIG=../lora-eval/config.yaml uv run python \
        probe_opencode_payload.py --prompt "покажи открытые mr" [--prompts-file probes.jsonl]
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from common import ROOT, load_config, sha256_file

OPENCODE_DIR = ROOT.parent / "train" / "data" / "contracts" / "opencode"
CAPTURE_PATH = OPENCODE_DIR / "capture-request.json"
SYSTEM_PATH = OPENCODE_DIR / "system-prompt.txt"


def load_prompts(args: argparse.Namespace) -> list[dict[str, str]]:
    prompts: list[dict[str, str]] = [
        {"id": f"cli-{index}", "prompt": prompt}
        for index, prompt in enumerate(args.prompt or [], 1)
    ]
    if args.prompts_file:
        for index, line in enumerate(Path(args.prompts_file).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            entry = json.loads(line)
            prompts.append({"id": entry.get("id", f"file-{index}"), "prompt": entry["prompt"]})
    if not prompts:
        raise SystemExit("pass at least one --prompt or --prompts-file")
    return prompts


def build_request(config: dict[str, Any], prompt: str) -> dict[str, Any]:
    """Frozen capture body with model, system prompt and user prompt replaced."""
    payload = copy.deepcopy(json.loads(CAPTURE_PATH.read_text(encoding="utf-8")))
    payload["model"] = config["endpoint"]["model_id"]
    payload["stream"] = False
    # stream_options is only valid with streaming; drop the captured user turn.
    payload.pop("stream_options", None)
    payload["messages"] = [
        {"role": "system", "content": SYSTEM_PATH.read_text(encoding="utf-8")},
        {"role": "user", "content": prompt},
    ]
    return payload


def summarize(body: dict[str, Any]) -> dict[str, Any]:
    message = (body.get("choices") or [{}])[0].get("message") or {}
    tool_calls = [
        {
            "name": (call.get("function") or {}).get("name"),
            "arguments": (call.get("function") or {}).get("arguments"),
        }
        for call in message.get("tool_calls") or []
    ]
    return {
        "finish_reason": (body.get("choices") or [{}])[0].get("finish_reason"),
        "tool_calls": tool_calls,
        "text": (message.get("content") or "")[:2000],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", action="append", help="Prompt to probe (repeatable)")
    parser.add_argument("--prompts-file", type=Path, help="JSONL of {id?, prompt}")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    config = load_config()
    prompts = load_prompts(args)
    url = f"{config['endpoint']['base_url'].removesuffix('/')}/chat/completions"
    run_dir = ROOT / "results" / f"probe-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    failures = 0
    with httpx.Client(timeout=args.timeout) as client:
        for entry in prompts:
            request = build_request(config, entry["prompt"])
            record = {
                "id": entry["id"],
                "prompt": entry["prompt"],
                "tools_sent": [tool["function"]["name"] for tool in request["tools"]],
            }
            started = time.monotonic()
            try:
                response = client.post(
                    url,
                    headers={"Authorization": f"Bearer {config['endpoint']['api_key']}"},
                    json=request,
                )
                record["status"] = response.status_code
                record["latency_s"] = round(time.monotonic() - started, 2)
                if response.is_success:
                    record.update(summarize(response.json()))
                else:
                    record["error_body"] = response.text[:2000]
                    failures += 1
            except httpx.HTTPError as exc:
                record["status"] = None
                record["error"] = f"{type(exc).__name__}: {exc}"
                failures += 1
            results.append(record)
            called = ",".join(t["name"] or "?" for t in record.get("tool_calls", [])) or "none"
            print(f"{record['id']}: status={record['status']} tools=[{called}]")

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": config["endpoint"]["model_id"],
        "base_url": config["endpoint"]["base_url"],
        "capture_sha256": sha256_file(CAPTURE_PATH),
        "system_prompt_sha256": sha256_file(SYSTEM_PATH),
        "prompts": len(prompts),
        "http_failures": failures,
        "results": results,
    }
    out_path = run_dir / "probe.json"
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out_path.relative_to(ROOT)} ({len(prompts)} probes, {failures} failures)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
