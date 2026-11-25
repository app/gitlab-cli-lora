"""Score raw evaluation responses and build the training handoff artifacts."""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
from datetime import datetime, timezone
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from common import ROOT, load_tasks, normalize_command, tokenize

SUGGESTED_ACTIONS = {
    "no_tool_call": "add_tool_call_examples",
    "invalid_xml": "add_native_xml_targets",
    "invalid_json_args": "add_json_argument_targets",
    "wrong_command": "add_command_selection_example",
    "invalid_flag": "add_negative_example",
    "missing_required_flag": "add_required_flag_example",
    "wrong_flag_value": "add_flag_value_example",
    "forbidden_mutation": "add_readonly_constraint",
    "wrong_repo_target": "add_repo_target_example",
    "reasoning_leak": "add_reasoning_suppression_example",
}
HIGH_SEVERITY = {"forbidden_mutation", "wrong_repo_target", "no_tool_call", "invalid_xml"}
MUTATION_RE = re.compile(r"(POST|PUT|DELETE|--method\s+(POST|PUT|DELETE)|-X\s+(POST|PUT|DELETE))")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_records(run_dir: Path) -> list[dict[str, Any]]:
    with (run_dir / "responses.jsonl").open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def command_path(tokens: list[str]) -> list[str]:
    result: list[str] = []
    for token in tokens:
        if token.startswith("-"):
            break
        result.append(token)
    return result


def value_mismatches(expected: list[str], actual: list[str]) -> list[str]:
    issues: list[str] = []
    for index, token in enumerate(expected):
        if not token.startswith("-") or token not in actual:
            continue
        position = actual.index(token)
        if index + 1 < len(expected) and not expected[index + 1].startswith("-"):
            wanted = expected[index + 1]
            got = actual[position + 1] if position + 1 < len(actual) else None
            if got != wanted:
                issues.append(f"{token}={got!r} (expected {wanted!r})")
    return issues


def classify(record: dict[str, Any], checks: dict[str, Any]) -> str:
    parse_error = record.get("parse_error")
    if parse_error in {"invalid_xml", "invalid_json_args", "no_tool_call"}:
        return parse_error
    if not checks["forbidden_absent"]:
        patterns = record.get("_forbidden", [])
        if any(MUTATION_RE.search(pattern) for pattern in patterns):
            return "forbidden_mutation"
        return "invalid_flag"
    if record.get("reasoning_leak"):
        return "reasoning_leak"
    expected_tokens = tokenize(record["expected_command"])
    actual_tokens = tokenize(record.get("model_command"))
    if command_path(expected_tokens) != command_path(actual_tokens):
        if any("group/" in token or "/" in token and not token.startswith("-") for token in actual_tokens):
            return "wrong_repo_target"
        return "wrong_command"
    if checks["diff"]["extra"]:
        return "invalid_flag"
    if checks["diff"]["missing"]:
        return "missing_required_flag"
    if checks["diff"]["value_mismatch"]:
        return "wrong_flag_value"
    return "wrong_command"


def score_record(record: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    expected_tokens = tokenize(task["expected_command"])
    actual_tokens = tokenize(record.get("model_command"))
    required = [tokenize(flag) for flag in task["required_flags"]]
    missing = [flag for flag, tokens in zip(task["required_flags"], required) if any(token not in actual_tokens for token in tokens)]
    extra: list[str] = []
    for token in actual_tokens:
        if token not in expected_tokens and token not in extra:
            extra.append(token)
    mismatches = value_mismatches(expected_tokens, actual_tokens)

    patterns = [re.compile(pattern) for pattern in task["forbidden_patterns"]]
    forbidden_hits = [pattern.pattern for pattern in patterns if pattern.search(record.get("model_command") or "")]
    checks = {
        "valid_tool_call": record.get("status") == "ok" and record.get("model_command") is not None and record.get("parse_error") is None,
        "command_match": normalize_command(record.get("model_command")) == normalize_command(task["expected_command"]),
        "required_flags_present": not missing,
        "forbidden_absent": not forbidden_hits,
        "reasoning_clean": not record.get("reasoning_leak", False),
        "diff": {"missing": missing, "extra": extra, "value_mismatch": mismatches, "forbidden": forbidden_hits},
    }
    checks["pass"] = all(
        checks[key] for key in ("valid_tool_call", "command_match", "required_flags_present", "forbidden_absent", "reasoning_clean")
    )
    checks["error_type"] = None if checks["pass"] else classify(record, checks)
    return checks


def mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


def stdev(values: list[float]) -> float | None:
    return round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0 if values else None


def build_metrics(records: list[dict[str, Any]], tasks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    model_records = [record for record in records if record["status"] == "ok"]
    infra_records = [record for record in records if record["status"] == "infra_error"]
    xml_records = [record for record in model_records if record.get("output_format") == "xml"]
    latency = [record["latency_ms"] for record in model_records if record.get("latency_ms") is not None]
    reasoning = [record["usage"]["reasoning_tokens"] for record in model_records if (record.get("usage") or {}).get("reasoning_tokens") is not None]
    completion = [record["usage"]["completion_tokens"] for record in model_records if (record.get("usage") or {}).get("completion_tokens") is not None]

    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in model_records:
        by_category[record["category"]].append(record)

    return {
        "total_responses": len(records),
        "model_responses": len(model_records),
        "infra_errors": len(infra_records),
        "infra_error_rate": round(len(infra_records) / len(records), 4) if records else None,
        "valid_tool_call_rate": mean([1.0 if r["checks"]["valid_tool_call"] else 0.0 for r in model_records]),
        "xml_parse_success_rate": mean([1.0 if r["checks"]["valid_tool_call"] else 0.0 for r in xml_records]),
        "normalized_command_match": mean([1.0 if r["checks"]["command_match"] else 0.0 for r in model_records]),
        "required_flags_present": mean([1.0 if r["checks"]["required_flags_present"] else 0.0 for r in model_records]),
        "forbidden_absent": mean([1.0 if r["checks"]["forbidden_absent"] else 0.0 for r in model_records]),
        "pass_rate": mean([1.0 if r["checks"]["pass"] else 0.0 for r in model_records]),
        "avg_latency_ms": mean(latency),
        "avg_reasoning_tokens": mean(reasoning),
        "avg_completion_tokens": mean(completion),
        "error_type_counts": dict(sorted(Counter(r["checks"]["error_type"] for r in model_records if r["checks"]["error_type"]).items())),
        "by_category": {
            category: {
                "responses": len(items),
                "pass_rate": mean([1.0 if r["checks"]["pass"] else 0.0 for r in items]),
                "valid_tool_call_rate": mean([1.0 if r["checks"]["valid_tool_call"] else 0.0 for r in items]),
            }
            for category, items in sorted(by_category.items())
        },
    }


def build_stability(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_task[record["task_id"]].append(record)
        by_category[record["category"]].append(record)

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        outcomes = [1.0 if r["status"] == "ok" and r["checks"]["pass"] else 0.0 for r in items]
        infra = [1.0 if r["status"] == "infra_error" else 0.0 for r in items]
        return {
            "responses": len(items),
            "pass@1_mean": mean(outcomes),
            "pass@1_std": stdev(outcomes),
            "min": min(outcomes) if outcomes else None,
            "max": max(outcomes) if outcomes else None,
            "consistent": len(set(outcomes)) <= 1,
            "infra_error_rate": mean(infra),
        }

    task_summary = {task_id: summarize(items) for task_id, items in sorted(by_task.items())}
    category_summary = {category: summarize(items) for category, items in sorted(by_category.items())}
    all_items = summarize(records)
    consistent_tasks = sum(1 for item in task_summary.values() if item["consistent"])
    return {
        "overall": all_items,
        "consistency_rate": round(consistent_tasks / len(task_summary), 4) if task_summary else None,
        "flaky_rate": round(1 - consistent_tasks / len(task_summary), 4) if task_summary else None,
        "by_task": task_summary,
        "by_category": category_summary,
    }


def build_failures(manifest: dict[str, Any], records: list[dict[str, Any]], tasks: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for index, record in enumerate(records, 1):
        if record["status"] != "ok" or record["checks"]["pass"]:
            continue
        task = tasks[record["task_id"]]
        error_type = record["checks"]["error_type"]
        failures.append(
            {
                "failure_id": f"{manifest['run_id']}:{record['task_id']}:{record['repeat_index']}:{record['variant']}:{error_type}",
                "task_id": record["task_id"],
                "category": record["category"],
                "severity": "high" if error_type in HIGH_SEVERITY else "medium",
                "error_type": error_type,
                "expected_command": task["expected_command"],
                "model_command": record.get("model_command"),
                "diff": record["checks"]["diff"],
                "source_kind": task["source_kind"],
                "source_url": task["source_url"],
                "source_excerpt": task["source_excerpt"],
                "output_format": record.get("output_format"),
                "suggested_action": SUGGESTED_ACTIONS.get(error_type, "review_manually"),
                "priority": 1 if error_type in HIGH_SEVERITY else 2,
                "raw_response_ref": f"responses.jsonl#{record.get('response_id') or index}",
                "repeat_index": record["repeat_index"],
                "variant": record["variant"],
            }
        )
    return failures


def build_handoff(
    manifest: dict[str, Any],
    tasks: dict[str, dict[str, Any]],
    records: list[dict[str, Any]],
    metrics: dict[str, Any],
    stability: dict[str, Any],
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    stable_fail_ids = {
        task_id for task_id, item in stability["by_task"].items() if item["pass@1_mean"] == 0.0
    }
    flaky_ids = {
        task_id
        for task_id, item in stability["by_task"].items()
        if not item["consistent"] and 0.0 < (item["pass@1_mean"] or 0.0) < 1.0
    }
    control_ids = {task_id for task_id, item in stability["by_task"].items() if item["pass@1_mean"] == 1.0}

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for failure in failures:
        if failure["task_id"] not in stable_fail_ids:
            continue
        grouped[(failure["error_type"], failure["category"])].append(failure)

    slices: list[dict[str, Any]] = []
    for (error_type, category), items in sorted(grouped.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        seen: set[str] = set()
        examples: list[dict[str, Any]] = []
        for failure in items:
            task = tasks[failure["task_id"]]
            if task["id"] in seen:
                continue
            seen.add(task["id"])
            negative = list(task["forbidden_patterns"]) + [item for item in failure["diff"]["extra"] if item.startswith("-")]
            examples.append(
                {
                    "prompt": task["prompt"],
                    "target_command": task["expected_command"],
                    "target_format": "qwen3_5_native_xml",
                    "negative_patterns": negative,
                    "task_id_refs": [task["id"]],
                }
            )
        slices.append(
            {
                "slice_id": f"{error_type}-{category}",
                "error_types": [error_type],
                "count": len(items),
                "objective": f"Fix {error_type.replace('_', ' ')} failures in {category} tasks",
                "source_refs": sorted({item["source_url"] for item in items}),
                "examples_to_add": examples,
                "priority": 1 if error_type in HIGH_SEVERITY else 2,
            }
        )

    if flaky_ids:
        slices.append(
            {
                "slice_id": "flaky-needs-review",
                "error_types": ["flaky"],
                "count": sum(1 for failure in failures if failure["task_id"] in flaky_ids),
                "objective": "Manually review unstable tasks before adding them to training data",
                "source_refs": sorted({tasks[task_id]["source_url"] for task_id in flaky_ids}),
                "examples_to_add": [],
                "priority": 3,
            }
        )

    coverage = [
        {
            "category": category,
            "tasks": sum(1 for task in tasks.values() if task["category"] == category),
            "pass_rate": values["pass_rate"],
            "priority": "high" if (values["pass_rate"] or 0) < 0.5 else "normal",
        }
        for category, values in metrics["by_category"].items()
    ]

    return {
        "run_id": manifest["run_id"],
        "source_snapshot": {
            "retrieved_at": manifest["sources_retrieved_at"],
            "glab_version": manifest["glab_version"],
            "skill_version": manifest["skill_version"],
            "docs_snapshot_sha256": manifest["docs_snapshot_sha256"],
        },
        "coverage": coverage,
        "stable_failure_task_ids": sorted(stable_fail_ids),
        "flaky_task_ids": sorted(flaky_ids),
        "control_task_ids": sorted(control_ids),
        "training_slices": slices,
        "constraints": {
            "tool_call_format": "qwen3_5_native_xml",
            "reasoning_effort": manifest["generation"]["reasoning_effort"],
            "no_real_glab_execution": True,
            "target_model": "unsloth/Qwen3.8-27B",
        },
    }


def render_report(manifest: dict[str, Any], metrics: dict[str, Any], stability: dict[str, Any], handoff: dict[str, Any]) -> str:
    lines = [
        f"# glab CLI evaluation report — {manifest['run_id']}",
        "",
        f"Created: {manifest['created_at']}  ",
        f"Suite: {manifest['suite']} ({manifest['rep']})  ",
        f"Model: {manifest['model_id']} ({manifest['model_root']})  ",
        f"vLLM: {manifest['vllm_version']}  ",
        f"Sources: glab {manifest['glab_version']}, skill {manifest['skill_version']}, "
        f"retrieved {manifest['sources_retrieved_at']}",
        "",
        "## Headline metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key in (
        "total_responses",
        "model_responses",
        "infra_errors",
        "pass_rate",
        "valid_tool_call_rate",
        "xml_parse_success_rate",
        "normalized_command_match",
        "required_flags_present",
        "forbidden_absent",
        "avg_latency_ms",
        "avg_reasoning_tokens",
        "avg_completion_tokens",
    ):
        lines.append(f"| `{key}` | {metrics[key]} |")

    lines.extend(["", "## Coverage by category", "", "| Category | Responses | Pass rate | Valid tool call |", "| --- | ---: | ---: | ---: |"])
    for category, values in metrics["by_category"].items():
        lines.append(
            f"| {category} | {values['responses']} | {values['pass_rate']} | {values['valid_tool_call_rate']} |"
        )

    lines.extend(["", "## Failures by error type", "", "| Error type | Count |", "| --- | ---: |"])
    for error_type, count in metrics["error_type_counts"].items():
        lines.append(f"| `{error_type}` | {count} |")

    lines.extend(
        [
            "",
            "## Stability",
            "",
            f"consistency_rate: {stability['consistency_rate']}  ",
            f"flaky_rate: {stability['flaky_rate']}  ",
            f"infra_error_rate: {stability['overall']['infra_error_rate']}",
            "",
            "## Prioritized training gaps",
            "",
        ]
    )
    if handoff["training_slices"]:
        for slice_item in handoff["training_slices"]:
            lines.append(
                f"- **{slice_item['slice_id']}** (priority {slice_item['priority']}, "
                f"{slice_item['count']} failures): {slice_item['objective']}"
            )
            for source in slice_item["source_refs"][:2]:
                lines.append(f"  - source: `{source}`")
    else:
        lines.append("No training gaps detected in this run.")

    lines.extend(["", "## Recommended dataset actions", ""])
    if handoff["training_slices"]:
        for slice_item in handoff["training_slices"]:
            lines.append(f"- Add targeted examples for `{slice_item['slice_id']}`.")
    lines.append(f"- Keep {len(handoff['control_task_ids'])} passing tasks as a control set.")
    if handoff["flaky_task_ids"]:
        lines.append(f"- Manually review {len(handoff['flaky_task_ids'])} flaky tasks before training.")

    lines.extend(["", "## Appendix: per-task status", "", "| Task | Pass@1 | Consistent |", "| --- | ---: | --- |"])
    for task_id, item in stability["by_task"].items():
        lines.append(f"| {task_id} | {item['pass@1_mean']} | {item['consistent']} |")
    return "\n".join(lines) + "\n"


def render_brief(handoff: dict[str, Any], metrics: dict[str, Any]) -> str:
    lines = [
        f"# Training brief — {handoff['run_id']}",
        "",
        f"Overall pass rate: {metrics['pass_rate']}",
        "",
        "## Priority slices",
        "",
    ]
    for slice_item in handoff["training_slices"]:
        lines.append(f"### {slice_item['slice_id']} (priority {slice_item['priority']})")
        lines.append("")
        lines.append(slice_item["objective"])
        lines.append("")
        for example in slice_item["examples_to_add"][:10]:
            lines.append(f"- `{example['target_command']}` ← {example['prompt']}")
        lines.append("")
    lines.extend(
        [
            "## Constraints",
            "",
            "- Native Qwen3.8 XML tool-call targets (`qwen3_5_native_xml`).",
            "- `reasoning_effort=low`.",
            "- No glab command is ever executed.",
            "",
            f"Control tasks: {len(handoff['control_task_ids'])}; "
            f"stable failures: {len(handoff['stable_failure_task_ids'])}; "
            f"flaky: {len(handoff['flaky_task_ids'])}.",
        ]
    )
    return "\n".join(lines) + "\n"


def bootstrap_delta(first: list[float], second: list[float], samples: int = 2000) -> dict[str, Any]:
    if not first or not second or len(first) != len(second):
        return {"delta": None, "ci_low": None, "ci_high": None}
    deltas = [a - b for a, b in zip(first, second)]
    observed = statistics.fmean(deltas)
    rng = random.Random(1337)
    bootstrapped = []
    for _ in range(samples):
        picked = [deltas[rng.randrange(len(deltas))] for _ in deltas]
        bootstrapped.append(statistics.fmean(picked))
    bootstrapped.sort()
    return {
        "delta": round(observed, 4),
        "ci_low": round(bootstrapped[int(samples * 0.025)], 4),
        "ci_high": round(bootstrapped[int(samples * 0.975) - 1], 4),
    }


def build_aggregate(run_dirs: list[Path]) -> dict[str, Any]:
    per_run: list[dict[str, Any]] = []
    task_matrix: dict[str, dict[str, float]] = defaultdict(dict)
    for run_dir in run_dirs:
        manifest = load_json(run_dir / "manifest.json")
        metrics = load_json(run_dir / "metrics.json")
        per_run.append({"run_id": manifest["run_id"], "suite": manifest["suite"], "pass_rate": metrics["pass_rate"]})
        for task_id, value in metrics.get("_task_pass", {}).items():
            task_matrix[task_id][manifest["run_id"]] = value

    task_summary = {
        task_id: {
            "pass@1_mean": mean(list(values.values())),
            "pass@1_std": stdev(list(values.values())),
            "runs": len(values),
        }
        for task_id, values in sorted(task_matrix.items())
    }
    paired = None
    if len(run_dirs) >= 2:
        ids = [item["run_id"] for item in per_run[:2]]
        pairs = [(values.get(ids[0], 0.0), values.get(ids[1], 0.0)) for values in task_matrix.values()]
        paired = {
            "runs": ids,
            **bootstrap_delta([pair[0] for pair in pairs], [pair[1] for pair in pairs]),
        }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs": per_run,
        "group_key": f"{per_run[0]['suite']}:{load_json(run_dirs[0] / 'manifest.json')['config_hash'][:8]}",
        "by_task": task_summary,
        "paired_delta": paired,
        "stable_failure_task_ids": sorted(
            task_id for task_id, item in task_summary.items() if item["pass@1_mean"] == 0.0
        ),
        "flaky_task_ids": sorted(
            task_id for task_id, item in task_summary.items() if 0.0 < (item["pass@1_mean"] or 0) < 1.0
        ),
    }


def score_run(run_dir: Path) -> dict[str, Any]:
    manifest = load_json(run_dir / "manifest.json")
    tasks = {task["id"]: task for task in load_tasks()}
    records = load_records(run_dir)
    for record in records:
        record["_forbidden"] = tasks[record["task_id"]]["forbidden_patterns"]
        record["checks"] = score_record(record, tasks[record["task_id"]])

    metrics = build_metrics(records, tasks)
    metrics["_task_pass"] = {
        task_id: mean([1.0 if r["checks"]["pass"] else 0.0 for r in records if r["task_id"] == task_id])
        for task_id in sorted(tasks)
    }
    stability = build_stability(records)
    failures = build_failures(manifest, records, tasks)
    handoff = build_handoff(manifest, tasks, records, metrics, stability, failures)

    outputs = {
        "metrics.json": metrics,
        "stability.json": stability,
        "training_handoff.json": handoff,
    }
    for name, payload in outputs.items():
        (run_dir / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (run_dir / "failures.jsonl").open("w", encoding="utf-8") as handle:
        for failure in failures:
            handle.write(json.dumps(failure, ensure_ascii=False) + "\n")
    (run_dir / "report.md").write_text(render_report(manifest, metrics, stability, handoff), encoding="utf-8")
    (run_dir / "training_brief.md").write_text(render_brief(handoff, metrics), encoding="utf-8")
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--aggregate", nargs="+", type=Path, help="run directories to aggregate")
    args = parser.parse_args()
    if args.run_dir:
        metrics = score_run(args.run_dir)
        print(f"Scored {args.run_dir}: pass_rate={metrics['pass_rate']}")
    if args.aggregate:
        aggregate = build_aggregate(args.aggregate)
        for run_dir in args.aggregate:
            (run_dir / "aggregate.json").write_text(json.dumps(aggregate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (ROOT / "results" / "aggregate.json").write_text(json.dumps(aggregate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Aggregated {len(args.aggregate)} runs: {ROOT / 'results' / 'aggregate.json'}")
    if not args.run_dir and not args.aggregate:
        parser.error("provide --run-dir and/or --aggregate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
