#!/usr/bin/env python3
"""Collect glab error usage from all OpenCode sessions.

Read-only: talks to the running OpenCode service through `opencode api get`.
Writes the corpus into this directory. See README.md for the rules.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
PURE_GLAB_CLASSES = ("cli_usage", "api_endpoint", "graphql", "repo_context")

# glab invocation detection -------------------------------------------------

HEREDOC_RE = re.compile(r"<<(?!<)-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")
ASSIGN_RE = re.compile(
    r"""^[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|'[^']*'|\S*)\s*"""
)
WRAPPERS = {"sudo", "env", "command", "nohup", "time", "exec"}
KEYWORDS = {"then", "do", "else", "elif", "if", "while", "until", "!", "{", "}"}


def strip_heredocs(command: str) -> str:
    """Drop heredoc bodies so that message text is not parsed as commands."""
    lines: list[str] = []
    terminator: str | None = None
    for line in command.splitlines():
        if terminator is not None:
            if line.strip() == terminator:
                terminator = None
            continue
        lines.append(line)
        match = HEREDOC_RE.search(line)
        if match:
            terminator = match.group(1)
    return "\n".join(lines)


def split_segments(text: str) -> list[str]:
    """Split shell text into command segments, respecting quotes and &&/||."""
    segments: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(text):
        char = text[i]
        if quote:
            buf.append(char)
            if char == "\\" and quote == '"' and i + 1 < len(text):
                buf.append(text[i + 1])
                i += 2
                continue
            if char == quote:
                quote = None
            i += 1
            continue
        if char in ("'", '"'):
            quote = char
            buf.append(char)
            i += 1
            continue
        if char == "\\":
            buf.append(char)
            if i + 1 < len(text):
                buf.append(text[i + 1])
                i += 2
                continue
            i += 1
            continue
        if char in ";|(){}`\n":
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        if char == "&":
            # `&&` separates commands; a single `&` belongs to redirection
            # (`2>&1`) or backgrounding and must stay inside the segment.
            if text[i : i + 2] == "&&":
                segments.append("".join(buf))
                buf = []
                i += 2
                continue
            buf.append(char)
            i += 1
            continue
        buf.append(char)
        i += 1
    segments.append("".join(buf))
    return [segment for segment in segments if segment.strip()]


def normalize_segment(segment: str) -> str:
    text = segment.strip()
    while True:
        match = ASSIGN_RE.match(text)
        if not match:
            break
        text = text[match.end() :].lstrip()
    parts = text.split(None, 1)
    while parts and parts[0] in WRAPPERS:
        wrapper = parts[0]
        text = parts[1].lstrip() if len(parts) > 1 else ""
        parts = text.split(None, 1)
        while parts and parts[0].startswith("-"):
            option = parts[0]
            text = parts[1].lstrip() if len(parts) > 1 else ""
            parts = text.split(None, 1)
            if wrapper == "sudo" and option in (
                "-u", "-g", "-p", "-h", "-C", "-U", "-r", "-t",
            ):
                # the option takes a separate argument
                text = parts[1].lstrip() if len(parts) > 1 else ""
                parts = text.split(None, 1)
    while parts and parts[0] in KEYWORDS:
        text = parts[1].lstrip() if len(parts) > 1 else ""
        parts = text.split(None, 1)
    return text


def glab_invocations(command: str) -> list[str]:
    """Return the glab command segments actually executed in a shell text."""
    found: list[str] = []
    for segment in split_segments(strip_heredocs(command)):
        text = normalize_segment(segment)
        first = text.split(None, 1)[0] if text else ""
        if first == "glab":
            found.append(text.strip())
    return found


# classification ------------------------------------------------------------

ENV_FS_RE = re.compile(r"Permission denied|No such file|command not found")
ENV_AUTH_RE = re.compile(
    r"insufficient_granular_scope|Access denied|API call failed|"
    r'"message":"[^"]*(?:401|403)|\b401 Unauthorized|\b403 Forbidden'
)
NETWORK_RE = re.compile(r"timeout|refused|TLS handshake|EOF|reset by peer", re.I)
CLI_USAGE_RE = re.compile(
    r"Unknown command|Unknown flag|Try --help|"
    r"Invalid .* format|invalid (?:value|argument)",
)
REPO_RE = re.compile(r"Could not determine base repository")
GRAPHQL_RE = re.compile(r'"errors"\s*:\s*\[')
API_RE = re.compile(r"HTTP 404|404 Not Found|\"error\"\s*:\s*\"404")
JQ_RE = re.compile(r"jq: (?:parse )?error")
JQ_ERR_RE = re.compile(r"jq: error")


def classify(status: str | None, exit_code, error_type: str | None, text: str):
    if error_type == "aborted":
        return "aborted", None
    if ENV_FS_RE.search(text):
        return "env_fs", "filesystem"
    if ENV_AUTH_RE.search(text):
        return "env_auth", "auth"
    if NETWORK_RE.search(text):
        return "network", "network"
    if CLI_USAGE_RE.search(text):
        return "cli_usage", None
    if REPO_RE.search(text):
        return "repo_context", None
    if GRAPHQL_RE.search(text):
        return "graphql", None
    if API_RE.search(text):
        return "api_endpoint", None
    if JQ_RE.search(text) or JQ_ERR_RE.search(text):
        return "pipeline_jq", None
    if status == "error":
        return "tool_error", error_type
    if isinstance(exit_code, int) and exit_code != 0:
        return "other_exit", f"exit_{exit_code}"
    return "ok", None


# API access ----------------------------------------------------------------


def api_get(path: str) -> dict:
    result = subprocess.run(
        ["opencode", "api", "get", path], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"opencode api get {path}: {result.stderr[:500]}")
    return json.loads(result.stdout)


def paginate(first: str, cursor_template: str):
    cursor: str | None = None
    while True:
        path = first if cursor is None else cursor_template.format(
            cursor=urllib.parse.quote(cursor)
        )
        page = api_get(path)
        yield from page["data"]
        cursor = (page.get("cursor") or {}).get("next")
        if not cursor:
            return


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    scan_started = datetime.now(timezone.utc)
    api_info = api_get("/api/info")
    sessions = list(paginate("/api/session", "/api/session?cursor={cursor}"))
    print(f"sessions: {len(sessions)}", file=sys.stderr)

    records: list[dict] = []
    turns: list[dict] = []
    errors: list[dict] = []
    scanned = 0

    for session in sessions:
        sid = session["id"]
        try:
            messages = list(
                paginate(
                    f"/api/session/{sid}/message?order=asc",
                    f"/api/session/{sid}/message?cursor={{cursor}}",
                )
            )
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"  ! {sid}: {exc}", file=sys.stderr)
            continue
        scanned += 1

        session_model = (session.get("model") or {}).get("id")
        context = {
            "session": sid,
            "project": session.get("projectID"),
            "directory": (session.get("location") or {}).get("directory"),
            "title": session.get("title"),
            "model": session_model,
        }

        prompt: str | None = None
        turn_no = -1
        turn_calls: list[dict] = []
        turn_text: list[str] = []

        def flush_turn() -> None:
            if turn_no >= 0 and turn_calls:
                turns.append(
                    {
                        **context,
                        "turn": turn_no,
                        "prompt": prompt,
                        "calls": [
                            {
                                "seq": call["seq"],
                                "msg": call["msg"],
                                "command": call["command"],
                                "invocations": call["invocations"],
                                "class": call["failure"],
                                "exit": call["exit"],
                            }
                            for call in turn_calls
                        ],
                        "final_text": "\n".join(turn_text)[:4000],
                    }
                )

        for index, message in enumerate(messages):
            mtype = message.get("type")
            if mtype == "user":
                flush_turn()
                prompt = message.get("text", "")
                turn_no += 1
                turn_calls = []
                turn_text = []
                continue
            if mtype != "assistant":
                continue
            for part in message.get("content", []):
                if part.get("type") == "text":
                    turn_text.append(part.get("text", ""))
                    continue
                if part.get("type") != "tool" or part.get("name") != "shell":
                    continue
                state = part.get("state") or {}
                inputs = state.get("input") or {}
                command = inputs.get("command") if isinstance(inputs, dict) else None
                if not isinstance(command, str):
                    continue
                invocations = glab_invocations(command)
                if not invocations:
                    continue

                output = "".join(
                    item.get("text", "")
                    for item in (state.get("content") or [])
                    if isinstance(item, dict) and item.get("type") == "text"
                )
                exit_code = (state.get("metadata") or {}).get("exit")
                error_type = (state.get("error") or {}).get("type")
                error_message = (state.get("error") or {}).get("message")
                failure, tag = classify(
                    state.get("status"), exit_code, error_type, output
                )
                record = {
                    **context,
                    "msg": message.get("id"),
                    "time": (message.get("time") or {}).get("created"),
                    "seq": index,
                    "turn": turn_no,
                    "prompt": prompt,
                    "workdir": inputs.get("workdir"),
                    "command": command,
                    "invocations": invocations,
                    "status": state.get("status"),
                    "exit": exit_code,
                    "error_type": error_type,
                    "error_message": error_message,
                    "failure": failure,
                    "failure_tag": tag,
                    "output": output,
                }
                records.append(record)
                turn_calls.append(record)

        flush_turn()

    # recovery: first successful glab call later in the same turn
    by_turn: defaultdict[tuple, list[dict]] = defaultdict(list)
    for record in records:
        by_turn[(record["session"], record["turn"])].append(record)
    for record in records:
        record["recovery"] = None
        if record["failure"] in PURE_GLAB_CLASSES:
            for later in by_turn[(record["session"], record["turn"])]:
                if later["seq"] > record["seq"] and later["failure"] == "ok":
                    record["recovery"] = {
                        "seq": later["seq"],
                        "command": later["command"],
                        "invocations": later["invocations"],
                    }
                    break

    # curated errors only
    for record in records:
        if record["failure"] not in PURE_GLAB_CLASSES:
            continue
        normalized = re.sub(r"\s+", " ", (record["output"] or "")).strip()[:400]
        key = hashlib.sha256(
            f"{' ; '.join(record['invocations'])}\n{normalized}".encode()
        ).hexdigest()[:16]
        errors.append(
            {
                "id": f"{record['session']}:{record['msg']}:{record['seq']}",
                "dedup_key": key,
                **{k: record[k] for k in (
                    "session", "project", "directory", "title", "model",
                    "msg", "time", "turn", "prompt", "workdir", "command",
                    "invocations", "exit", "failure", "failure_tag", "output",
                    "recovery",
                )},
            }
        )

    # write outputs
    def write_jsonl(name: str, rows: list[dict]) -> None:
        with (OUT_DIR / name).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    write_jsonl("records.jsonl", records)
    write_jsonl("turns.jsonl", turns)
    write_jsonl("errors.jsonl", errors)

    class_counts = Counter(record["failure"] for record in records)
    summary = {
        "scanned_at": scan_started.isoformat(),
        "opencode_version": api_info.get("version"),
        "sessions_total": len(sessions),
        "sessions_scanned": scanned,
        "sessions_with_glab": len({record["session"] for record in records}),
        "glab_invocations": len(records),
        "turns_with_glab": len(turns),
        "class_counts": dict(class_counts.most_common()),
        "pure_glab_errors": len(errors),
        "sessions_with_errors": len({record["session"] for record in errors}),
        # exact prompt strings; the useful deduplicated count is `dedup_keys`
        "unique_error_prompt_texts": len({record["prompt"] for record in errors}),
        "errors_with_recovery": sum(1 for record in errors if record["recovery"]),
        # curated errors per pure glab class (`failure_tag` is only set for
        # env/tool classes, so it cannot describe the curated set)
        "by_class": dict(
            Counter(record["failure"] for record in errors).most_common()
        ),
        "by_project": dict(
            Counter(record["directory"] for record in errors).most_common()
        ),
        "by_model": dict(Counter(record["model"] for record in errors).most_common()),
        "dedup_keys": len({record["dedup_key"] for record in errors}),
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    outputs = ["records.jsonl", "turns.jsonl", "errors.jsonl"]
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "opencode api get /api/session and /api/session/{id}/message",
        "opencode_version": api_info.get("version"),
        "sessions_total": len(sessions),
        "sessions_scanned": scanned,
        "pure_glab_classes": list(PURE_GLAB_CLASSES),
        "sha256": {name: sha256(OUT_DIR / name) for name in outputs},
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
