"""Validate every task against the frozen documentation snapshots."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from common import ROOT, load_sources, load_tasks, sha256_file, tokenize

ALLOWED_KINDS = {"docs", "skill", "help"}
ALLOWED_CATEGORIES = {"issue", "mr", "ci", "api", "error", "safety"}


def validate() -> tuple[list[str], dict[str, Any]]:
    tasks = load_tasks()
    sources = load_sources()
    by_url = {item["url"]: item for item in sources["sources"]}
    errors: list[str] = []
    verified: set[str] = set()

    ids: set[str] = set()
    for task in tasks:
        task_id = task.get("id", f"line {task.get('_line')}")
        prefix = f"{task_id}:"
        for field in (
            "id",
            "category",
            "prompt",
            "expected_command",
            "required_flags",
            "forbidden_patterns",
            "source_kind",
            "source_url",
            "source_excerpt",
        ):
            if field not in task:
                errors.append(f"{prefix} missing field {field}")

        if task_id in ids:
            errors.append(f"{prefix} duplicate id")
        ids.add(task_id)

        if task.get("category") not in ALLOWED_CATEGORIES:
            errors.append(f"{prefix} unknown category {task.get('category')!r}")

        expected = task.get("expected_command", "")
        if not isinstance(expected, str) or not expected.startswith("glab "):
            errors.append(f"{prefix} expected_command must start with 'glab '")

        expected_tokens = tokenize(expected)
        for flag in task.get("required_flags", []):
            flag_tokens = tokenize(flag)
            if not flag_tokens or any(token not in expected_tokens for token in flag_tokens):
                errors.append(f"{prefix} required flag {flag!r} is absent from expected_command")

        compiled: list[re.Pattern[str]] = []
        for pattern in task.get("forbidden_patterns", []):
            try:
                compiled.append(re.compile(pattern))
            except re.error as exc:
                errors.append(f"{prefix} invalid regex {pattern!r}: {exc}")
        for pattern in compiled:
            if pattern.search(expected):
                errors.append(f"{prefix} expected_command matches forbidden pattern {pattern.pattern!r}")

        kind = task.get("source_kind")
        if kind not in ALLOWED_KINDS:
            errors.append(f"{prefix} unknown source_kind {kind!r}")
            continue

        source = by_url.get(task.get("source_url"))
        if source is None:
            errors.append(f"{prefix} source_url is not in docs/sources.json")
            continue
        if source["kind"] != kind:
            errors.append(f"{prefix} source_kind {kind!r} does not match snapshot kind {source['kind']!r}")
            continue

        snapshot = ROOT / "docs" / source["file"]
        if not snapshot.is_file():
            errors.append(f"{prefix} snapshot is missing: {snapshot}")
            continue
        digest = sha256_file(snapshot)
        if digest != source["sha256"]:
            errors.append(f"{prefix} snapshot sha256 changed for {source['file']}")
        verified.add(source["file"])

        excerpt = task.get("source_excerpt", "")
        if not isinstance(excerpt, str) or excerpt not in snapshot.read_text(encoding="utf-8"):
            errors.append(f"{prefix} source_excerpt not found verbatim in {source['file']}")

    summary = {
        "status": "ok" if not errors else "failed",
        "tasks": len(tasks),
        "categories": dict(sorted(Counter(task.get("category", "?") for task in tasks).items())),
        "source_kinds": dict(sorted(Counter(task.get("source_kind", "?") for task in tasks).items())),
        "snapshots_verified": len(verified),
        "errors": errors,
    }
    return errors, summary


PARITY_FIELDS = (
    "category",
    "expected_command",
    "required_flags",
    "forbidden_patterns",
    "source_kind",
    "source_url",
    "source_excerpt",
)


def validate_parity() -> list[str]:
    """Check that the Russian task set mirrors the English one exactly."""
    ru_path = ROOT / "tasks.ru.jsonl"
    if not ru_path.is_file():
        return [f"missing {ru_path.name}"]
    en = {task["id"]: task for task in load_tasks(ROOT / "tasks.jsonl")}
    ru = {task["id"]: task for task in load_tasks(ru_path)}
    errors: list[str] = []
    if set(en) != set(ru):
        errors.append(
            f"task id mismatch: only_en={sorted(set(en) - set(ru))} "
            f"only_ru={sorted(set(ru) - set(en))}"
        )
    for task_id in sorted(set(en) & set(ru)):
        for field in PARITY_FIELDS:
            if en[task_id].get(field) != ru[task_id].get(field):
                errors.append(f"{task_id}: {field} differs between en and ru")
        if en[task_id].get("prompt") == ru[task_id].get("prompt"):
            errors.append(f"{task_id}: ru prompt equals the en prompt")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print a JSON summary")
    parser.add_argument(
        "--no-parity",
        action="store_true",
        help="skip the English/Russian parity check",
    )
    args = parser.parse_args()
    errors, summary = validate()
    if not args.no_parity:
        parity_errors = validate_parity()
        errors.extend(parity_errors)
        summary["parity_errors"] = parity_errors
    summary["status"] = "ok" if not errors else "failed"
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        print(
            f"Validated {summary['tasks']} tasks against {summary['snapshots_verified']} snapshots: "
            f"{summary['status']}"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
