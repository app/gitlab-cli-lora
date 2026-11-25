"""Send text-only glab prompts to the local vLLM endpoint and store raw responses."""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from common import (
    ROOT,
    build_tool,
    canonical_hash,
    load_config,
    load_sources,
    load_tasks,
    parse_model_output,
    sha256_bytes,
    sha256_file,
    tasks_path,
    tool_schema_sha256,
)
from validate_tasks import validate


def docs_snapshot_sha256() -> str:
    sources = load_sources()
    payload = "\n".join(f"{item['file']}:{item['sha256']}" for item in sorted(sources["sources"], key=lambda x: x["file"]))
    return sha256_bytes(payload.encode())


def preflight(client: httpx.AsyncClient, config: dict[str, Any]) -> dict[str, Any]:
    endpoint = config["endpoint"]
    base_url = endpoint["base_url"].removesuffix("/")
    root_url = base_url.removesuffix("/v1")
    version_response = client.get(f"{root_url}/version")
    version_response.raise_for_status()
    version = version_response.json().get("version")
    if version != endpoint["vllm_version"]:
        raise RuntimeError(f"vLLM version mismatch: got {version!r}, expected {endpoint['vllm_version']!r}")

    models_response = client.get(f"{base_url}/models")
    models_response.raise_for_status()
    models = models_response.json().get("data", [])
    match = next((item for item in models if item.get("id") == endpoint["model_id"]), None)
    if match is None:
        raise RuntimeError(f"served model id {endpoint['model_id']!r} not found in /v1/models")
    if match.get("root") != endpoint["model_root"]:
        raise RuntimeError(f"model root mismatch: got {match.get('root')!r}, expected {endpoint['model_root']!r}")
    return {"vllm_version": version, "model_id": match["id"], "model_root": match["root"], "max_model_len": match.get("max_model_len")}


def load_shell_assets(config: dict[str, Any]) -> dict[str, Any]:
    """Frozen OpenCode serving contract used by the shell eval mode."""
    section = config.get("shell_mode") or {}
    system_path = (
        ROOT / section.get("system_prompt", "../train/data/contracts/opencode/system-prompt.txt")
    ).resolve()
    tool_path = (
        ROOT / section.get("tool", "../train/data/contracts/opencode/shell-tool.json")
    ).resolve()
    return {
        "system_prompt": system_path.read_text(encoding="utf-8"),
        "tool": json.loads(tool_path.read_text(encoding="utf-8")),
        "system_prompt_sha256": sha256_file(system_path),
        "tool_sha256": sha256_file(tool_path),
    }


def build_payload(
    config: dict[str, Any],
    prompt: str,
    variant: str,
    shell: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generation = config["generation"]
    payload: dict[str, Any] = {
        "model": config["endpoint"]["model_id"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": generation["temperature"],
        "reasoning_effort": generation["reasoning_effort"],
        "max_tokens": generation["max_tokens"],
    }
    if generation.get("seed") is not None:
        payload["seed"] = generation["seed"]
    if variant == "api":
        payload["tools"] = [build_tool(config)]
    elif variant == "shell":
        if shell is None:
            raise ValueError("shell variant requires the frozen shell assets")
        payload["messages"].insert(
            0, {"role": "system", "content": shell["system_prompt"]}
        )
        payload["tools"] = [shell["tool"]]
    else:
        payload["messages"].insert(0, {"role": "system", "content": config["raw_mode_system_prompt"]})
    return payload


async def send_one(
    client: httpx.AsyncClient,
    config: dict[str, Any],
    task: dict[str, Any],
    repeat_index: int,
    variant: str,
    shell: dict[str, Any] | None,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    runtime = config["runtime"]
    url = f"{config['endpoint']['base_url'].removesuffix('/')}/chat/completions"
    payload = build_payload(config, task["prompt"], variant, shell)
    record: dict[str, Any] = {
        "task_id": task["id"],
        "category": task["category"],
        "prompt": task["prompt"],
        "repeat_index": repeat_index,
        "variant": variant,
        "expected_command": task["expected_command"],
        "status": "ok",
        "error": None,
    }
    async with semaphore:
        for attempt in range(runtime["retries"] + 1):
            started = time.perf_counter()
            try:
                response = await client.post(url, json=payload)
                record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}", request=response.request, response=response
                    )
                response.raise_for_status()
                body = response.json()
                message = (body.get("choices") or [{}])[0].get("message") or {}
                parsed = parse_model_output({"message": message})
                tool_calls = message.get("tool_calls") or []
                tool_name = (
                    (tool_calls[0].get("function") or {}).get("name")
                    if tool_calls
                    else None
                )
                if variant == "shell":
                    # In shell mode the contract IS the tool name: a call to
                    # any other tool (for example the retired
                    # run_glab_command) fails even if the command matches.
                    if tool_name != "shell":
                        parsed["command"] = None
                        parsed["parse_error"] = (
                            "wrong_tool" if tool_name else "no_tool_call"
                        )
                usage = body.get("usage") or {}
                details = usage.get("completion_tokens_details") or {}
                record.update(
                    {
                        "raw_text": message.get("content") or "",
                        "api_tool_calls": message.get("tool_calls") or [],
                        "tool_name": tool_name,
                        "reasoning": parsed["reasoning"],
                        "model_command": parsed["command"],
                        "normalized_command": " ".join(parsed["command"].split()) if parsed["command"] else None,
                        "output_format": parsed["output_format"],
                        "parse_error": parsed["parse_error"],
                        "reasoning_leak": parsed["reasoning_leak"],
                        "visible_text": parsed["visible_text"],
                        "usage": {
                            "prompt_tokens": usage.get("prompt_tokens"),
                            "completion_tokens": usage.get("completion_tokens"),
                            "reasoning_tokens": details.get("reasoning_tokens"),
                        },
                        "finish_reason": (body.get("choices") or [{}])[0].get("finish_reason"),
                        "response_id": body.get("id"),
                        "attempt": attempt,
                    }
                )
                return record
            except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
                record["status"] = "infra_error"
                record.setdefault("latency_ms", round((time.perf_counter() - started) * 1000, 2))
                if attempt < runtime["retries"]:
                    await asyncio.sleep(runtime["retry_backoff_s"] * (2**attempt))
        return record


def update_index(run_id: str, suite: str, config_hash: str) -> None:
    path = ROOT / "results" / "index.json"
    index: dict[str, Any] = {"suites": {}}
    if path.is_file():
        try:
            index = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    suite_data = index.setdefault("suites", {}).setdefault(suite, {"runs": []})
    runs = [item for item in suite_data.get("runs", []) if item.get("run_id") != run_id]
    runs.insert(0, {"run_id": run_id, "config_hash": config_hash, "created_at": datetime.now(timezone.utc).isoformat()})
    suite_data["runs"] = runs[:20]
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


async def run(args: argparse.Namespace) -> int:
    config = load_config()
    errors, validation = validate()
    if errors:
        print("Task validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 2

    tasks = load_tasks()
    if args.category:
        tasks = [task for task in tasks if task["category"] in args.category.split(",")]
    if args.limit:
        tasks = tasks[: args.limit]
    if not tasks:
        print("No tasks selected", file=sys.stderr)
        return 2

    mode = args.mode or config["runtime"]["mode"]
    variants = ["api", "raw"] if mode == "both" else [mode]
    shell = load_shell_assets(config) if "shell" in variants else None
    repeats = args.repeats or config["runtime"]["repeats"]
    rep = args.rep if args.rep.startswith("r") else f"r{args.rep}"
    config_hash = canonical_hash(config)
    created_at = datetime.now(timezone.utc)
    timestamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    run_id = args.run_id or f"{args.suite}-{timestamp}-{config_hash[:8]}-{rep}"
    run_dir = ROOT / "results" / run_id
    if run_dir.exists() and not args.force:
        print(f"Run directory already exists: {run_dir} (use --force)", file=sys.stderr)
        return 2

    requested = len(tasks) * repeats * len(variants)
    print(f"run_id={run_id} tasks={len(tasks)} repeats={repeats} variants={variants} requests={requested}")
    if args.dry_run:
        return 0

    run_dir.mkdir(parents=True, exist_ok=args.force)

    with httpx.Client(timeout=config["runtime"]["timeout_s"]) as sync_client:
        try:
            preflight_info = preflight(sync_client, config)
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            print(f"Preflight failed: {exc}", file=sys.stderr)
            return 3

    sources = load_sources()
    script_hashes = {
        name: sha256_file(ROOT / name)
        for name in ("common.py", "run_eval.py", "score.py", "validate_tasks.py")
    }
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "suite": args.suite,
        "rep": rep,
        "created_at": created_at.isoformat(),
        "config_hash": config_hash,
        "config_short_hash": config_hash[:8],
        "endpoint": config["endpoint"]["base_url"],
        "model_id": config["endpoint"]["model_id"],
        "model_root": preflight_info["model_root"],
        "vllm_version": preflight_info["vllm_version"],
        "max_model_len": preflight_info["max_model_len"],
        "chat_template_sha256": sha256_file(ROOT / config["paths"]["chat_template"]),
        "tool_schema_sha256": tool_schema_sha256(config),
        "parser_version": config["versions"]["parser_version"],
        "normalization_version": config["versions"]["normalization_version"],
        "repeats": repeats,
        "seed": config["generation"].get("seed"),
        "generation": config["generation"],
        "mode": mode,
        "concurrency": config["runtime"]["concurrency"],
        "timeout_s": config["runtime"]["timeout_s"],
        "retries": config["runtime"]["retries"],
        "python_version": platform.python_version(),
        "glab_version": config["versions"]["glab_version"],
        "skill_version": config["versions"]["skill_version"],
        "docs_snapshot_sha256": docs_snapshot_sha256(),
        "sources_retrieved_at": sources["retrieved_at"],
        "validation_status": validation["status"],
        "validation_summary": validation,
        "tasks_file": str(tasks_path().relative_to(ROOT)),
        "tasks_sha256": sha256_file(tasks_path()),
        "script_sha256": script_hashes,
        "requested_responses": requested,
    }
    if shell is not None:
        manifest["shell_mode"] = {
            "system_prompt_sha256": shell["system_prompt_sha256"],
            "tool_sha256": shell["tool_sha256"],
        }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    semaphore = asyncio.Semaphore(config["runtime"]["concurrency"])
    limits = httpx.Limits(max_connections=config["runtime"]["concurrency"])
    timeout = httpx.Timeout(config["runtime"]["timeout_s"])
    headers = {"Authorization": f"Bearer {config['endpoint']['api_key']}"}
    async with httpx.AsyncClient(headers=headers, timeout=timeout, limits=limits) as client:
        jobs = [
            send_one(client, config, task, repeat_index, variant, shell, semaphore)
            for task in tasks
            for repeat_index in range(repeats)
            for variant in variants
        ]
        records = await asyncio.gather(*jobs)

    records.sort(key=lambda item: (item["task_id"], item["repeat_index"], item["variant"]))
    with (run_dir / "responses.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    update_index(run_id, args.suite, config_hash)
    infra = sum(1 for record in records if record["status"] == "infra_error")
    print(f"Wrote {len(records)} responses to {run_dir} (infra errors: {infra})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="baseline")
    parser.add_argument("--rep", default="r1")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--category")
    parser.add_argument("--mode", choices=["api", "raw", "shell", "both"])
    parser.add_argument("--repeats", type=int)
    parser.add_argument("--run-id")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
