"""Compare aggregated LoRA adapter results against the frozen baseline.

Both inputs are ``aggregate.json`` files produced by ``glab-eval/score.py``.
The script is dependency-free and writes ``compare.json`` and ``compare.md``
into the LoRA results directory.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_BASELINE = ROOT / "glab-eval" / "results" / "aggregate.json"
DEFAULT_ADAPTER = ROOT / "lora-eval" / "results" / "aggregate.json"
DEFAULT_OUTPUT = ROOT / "lora-eval" / "results"
TASKS = ROOT / "glab-eval" / "tasks.jsonl"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_categories() -> dict[str, str]:
    categories: dict[str, str] = {}
    with TASKS.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                task = json.loads(line)
                categories[task["id"]] = task.get("category", "")
    return categories


def suite_summary(aggregate: dict[str, Any]) -> dict[str, Any]:
    runs = aggregate.get("runs", [])
    return {
        "group_key": aggregate.get("group_key"),
        "runs": len(runs),
        "run_pass_rates": [run["pass_rate"] for run in runs],
        "mean_pass_rate": round(mean([run["pass_rate"] for run in runs]), 4) if runs else None,
        "stable_failure_task_ids": aggregate.get("stable_failure_task_ids", []),
        "flaky_task_ids": aggregate.get("flaky_task_ids", []),
    }


def classify(baseline: float, adapter: float) -> str:
    if baseline == 0.0 and adapter == 0.0:
        return "still_failing"
    if baseline == 1.0 and adapter == 1.0:
        return "stable_pass"
    if baseline == 0.0 and adapter == 1.0:
        return "fixed"
    if baseline < 1.0 and adapter == 1.0:
        return "stabilized"
    if baseline == 1.0 and adapter < 1.0:
        return "regressed"
    if adapter > baseline:
        return "improved"
    if adapter < baseline:
        return "degraded"
    return "unchanged"


def build_comparison(baseline: dict[str, Any], adapter: dict[str, Any]) -> dict[str, Any]:
    categories = load_categories()
    baseline_tasks = baseline.get("by_task", {})
    adapter_tasks = adapter.get("by_task", {})
    task_ids = sorted(set(baseline_tasks) | set(adapter_tasks))

    by_task: dict[str, Any] = {}
    status_counts: dict[str, int] = {}
    for task_id in task_ids:
        before = baseline_tasks.get(task_id, {}).get("pass@1_mean", 0.0)
        after = adapter_tasks.get(task_id, {}).get("pass@1_mean", 0.0)
        status = classify(before, after)
        status_counts[status] = status_counts.get(status, 0) + 1
        by_task[task_id] = {
            "category": categories.get(task_id, ""),
            "baseline_mean": before,
            "adapter_mean": after,
            "delta": round(after - before, 4),
            "status": status,
        }

    baseline_summary = suite_summary(baseline)
    adapter_summary = suite_summary(adapter)
    baseline_failures = set(baseline_summary["stable_failure_task_ids"])
    adapter_failures = set(adapter_summary["stable_failure_task_ids"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline": baseline_summary,
        "adapter": adapter_summary,
        "pass_rate_delta": round(adapter_summary["mean_pass_rate"] - baseline_summary["mean_pass_rate"], 4),
        "status_counts": status_counts,
        "fixed_baseline_failures": sorted(
            task_id for task_id in baseline_failures if by_task[task_id]["adapter_mean"] == 1.0
        ),
        "remaining_adapter_failures": sorted(adapter_failures),
        "regressed_tasks": sorted(task_id for task_id, row in by_task.items() if row["status"] == "regressed"),
        "by_task": by_task,
    }


def render_markdown(comparison: dict[str, Any]) -> str:
    baseline = comparison["baseline"]
    adapter = comparison["adapter"]
    lines = [
        "# glab LoRA evaluation comparison",
        "",
        f"Generated: `{comparison['generated_at']}`",
        "",
        "| Suite | Runs | Mean pass rate | Stable failures | Flaky tasks |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| Baseline (`{baseline['group_key']}`) | {baseline['runs']} | {baseline['mean_pass_rate']:.4f} | "
        f"{len(baseline['stable_failure_task_ids'])} | {len(baseline['flaky_task_ids'])} |",
        f"| Adapter (`{adapter['group_key']}`) | {adapter['runs']} | {adapter['mean_pass_rate']:.4f} | "
        f"{len(adapter['stable_failure_task_ids'])} | {len(adapter['flaky_task_ids'])} |",
        "",
        f"Absolute pass-rate delta: **{comparison['pass_rate_delta']:+.4f}**.",
        "",
        "## Outcome",
        "",
    ]
    for status, count in sorted(comparison["status_counts"].items()):
        lines.append(f"- `{status}`: {count}")
    lines.extend(
        [
            "",
            "## Baseline failures fixed by the adapter",
            "",
        ]
    )
    lines.extend(f"- `{task_id}`" for task_id in comparison["fixed_baseline_failures"])
    if not comparison["fixed_baseline_failures"]:
        lines.append("- none")
    lines.extend(["", "## Remaining adapter failures", ""])
    lines.extend(f"- `{task_id}`" for task_id in comparison["remaining_adapter_failures"])
    if not comparison["remaining_adapter_failures"]:
        lines.append("- none")
    lines.extend(["", "## Regressions", ""])
    lines.extend(f"- `{task_id}`" for task_id in comparison["regressed_tasks"])
    if not comparison["regressed_tasks"]:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Per-task results",
            "",
            "| Task | Category | Baseline | Adapter | Delta | Status |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for task_id, row in comparison["by_task"].items():
        lines.append(
            f"| `{task_id}` | {row['category']} | {row['baseline_mean']:.4f} | "
            f"{row['adapter_mean']:.4f} | {row['delta']:+.4f} | {row['status']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--adapter", type=Path, default=DEFAULT_ADAPTER)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    comparison = build_comparison(load_json(args.baseline), load_json(args.adapter))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "compare.json").write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.output_dir / "compare.md").write_text(render_markdown(comparison), encoding="utf-8")
    print(
        f"baseline={comparison['baseline']['mean_pass_rate']:.4f} "
        f"adapter={comparison['adapter']['mean_pass_rate']:.4f} "
        f"delta={comparison['pass_rate_delta']:+.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
