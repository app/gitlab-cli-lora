"""Validate the generated glab SFT datasets against frozen evaluation artifacts.

Covers both tool shapes: ``glab`` (run_glab_command) and ``shell`` (the frozen
OpenCode serving contract under train/data/contracts/opencode/).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "glab-eval"
DATA_ROOT = ROOT / "train" / "data"
OPENCODE_DIR = DATA_ROOT / "contracts" / "opencode"
sys.path.insert(0, str(EVAL_ROOT))
sys.path.insert(0, str(ROOT / "train"))

from build_dataset import (  # noqa: E402
    CONTROL_PARAPHRASES,
    FAILURE_PARAPHRASES,
    SHELL_SOURCE_NAMES,
    URL_FAMILY_PATH,
    URL_PHRASINGS_PATH,
    canonical_tool_sha,
    ext_rows,
    make_environment,
    paraphrase_path,
    render_example,
    shell_assets,
    url_family_rows,
)
from common import (  # noqa: E402
    FUNCTION_RE,
    PARAMETER_RE,
    build_tool,
    load_config,
    load_tasks,
    sha256_file,
    tool_schema_sha256,
)

MUTATING_RE = re.compile(
    r"(?:--method|-X)\s+(?:POST|PUT|DELETE|PATCH)|\b(?:create|delete|update|reopen|close|merge|approve|push|edit)\b",
    re.IGNORECASE,
)
EXPECTED_PREFIX = "<|im_start|>assistant\n<think>\n\n</think>\n\n<tool_call>\n"
# label, dataset dir under train/data (family/shape/lang), shape, language
DATASETS = (
    ("glab-en", "tasks/glab/en", "glab", "en"),
    ("glab-ru", "tasks/glab/ru", "glab", "ru"),
    ("shell-en", "tasks/shell/en", "shell", "en"),
    ("shell-ru", "tasks/shell/ru", "shell", "ru"),
)
URL_DATASETS = (
    ("url-glab-en", "url/glab/en", "glab", "en"),
    ("url-glab-ru", "url/glab/ru", "glab", "ru"),
    ("url-shell-en", "url/shell/en", "shell", "en"),
    ("url-shell-ru", "url/shell/ru", "shell", "ru"),
)
EXT_DATASETS = (
    ("ext-shell-en", "ext/shell/en", "shell", "en"),
    ("ext-shell-ru", "ext/shell/ru", "shell", "ru"),
)


def eval_prompts() -> set[str]:
    prompts = {task["prompt"] for task in load_tasks()}
    ru_path = EVAL_ROOT / "tasks.ru.jsonl"
    if ru_path.is_file():
        prompts |= {task["prompt"] for task in load_tasks(ru_path)}
    return prompts


def validate(label: str, rel_dir: str, shape: str, lang: str) -> list[str]:
    data_dir = DATA_ROOT / rel_dir
    output_path = data_dir / "sft.jsonl"
    manifest_path = data_dir / "dataset_manifest.json"
    paraphrase_file = paraphrase_path(lang)

    errors: list[str] = []
    config = load_config()
    tasks = load_tasks()
    task_by_id = {task["id"]: task for task in tasks}
    if shape == "shell":
        tool, system_prompt = shell_assets()
    else:
        tool, system_prompt = build_tool(config), None
    original_prompts = eval_prompts()

    handoff_run = json.loads((EVAL_ROOT / "results" / "index.json").read_text())[
        "suites"
    ]["baseline"]["runs"][0]["run_id"]
    handoff_path = EVAL_ROOT / "results" / handoff_run / "training_handoff.json"
    handoff = json.loads(handoff_path.read_text())
    failure_ids = set(handoff["stable_failure_task_ids"])
    control_ids = set(handoff["control_task_ids"])

    if not output_path.is_file():
        return [f"{label}: missing {output_path}"]
    if not manifest_path.is_file():
        return [f"{label}: missing {manifest_path}"]

    manifest = json.loads(manifest_path.read_text())
    if manifest.get("lang") != lang:
        errors.append(f"{label}: manifest lang is {manifest.get('lang')!r}")
    if manifest.get("shape", "glab") != shape:
        errors.append(f"{label}: manifest shape is {manifest.get('shape')!r}")

    expected_hashes = {
        "tasks.jsonl": EVAL_ROOT / "tasks.jsonl",
        "chat_template.jinja": EVAL_ROOT / "docs" / "chat_template.jinja",
        "training_handoff.json": handoff_path,
        "paraphrases.jsonl": paraphrase_file,
        "build_dataset.py": ROOT / "train" / "build_dataset.py",
    }
    if shape == "glab":
        expected_hashes["config.yaml"] = EVAL_ROOT / "config.yaml"
    else:
        expected_hashes.update(
            {name: OPENCODE_DIR / name for name in SHELL_SOURCE_NAMES}
        )
    if (EVAL_ROOT / "tasks.ru.jsonl").is_file():
        expected_hashes["tasks.ru.jsonl"] = EVAL_ROOT / "tasks.ru.jsonl"
    for name, path in expected_hashes.items():
        actual = sha256_file(path)
        if manifest["source_sha256"].get(name) != actual:
            errors.append(f"{label}: manifest source hash stale for {name}")
    manifest_tool_sha = (
        canonical_tool_sha(tool) if shape == "shell" else tool_schema_sha256(config)
    )
    if manifest["tool_schema_sha256"] != manifest_tool_sha:
        errors.append(f"{label}: manifest tool schema hash does not match the tool")

    template = make_environment().from_string(
        (EVAL_ROOT / "docs" / "chat_template.jinja").read_text()
    )

    examples: list[dict[str, Any]] = []
    with output_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                examples.append(json.loads(line))
            except json.JSONDecodeError as exc:
                errors.append(f"{label}: line {line_number}: invalid JSON ({exc})")

    seen_ids: set[str] = set()
    seen_prompts: set[str] = set()
    per_task: dict[str, int] = {}

    for index, example in enumerate(examples, 1):
        label_id = f"{label}: example {index} ({example.get('id', '?')})"
        example_id = example.get("id")
        if example_id in seen_ids:
            errors.append(f"{label_id}: duplicate id")
        seen_ids.add(example_id)

        if example.get("shape", "glab") != shape:
            errors.append(f"{label_id}: row shape is {example.get('shape')!r}")

        task_id = example.get("task_id")
        task = task_by_id.get(task_id)
        if task is None:
            errors.append(f"{label_id}: unknown task_id {task_id!r}")
            continue
        per_task[task_id] = per_task.get(task_id, 0) + 1

        prompt = example.get("prompt", "")
        if prompt in original_prompts:
            errors.append(f"{label_id}: prompt is an original eval prompt")
        if prompt in seen_prompts:
            errors.append(f"{label_id}: duplicate prompt")
        seen_prompts.add(prompt)

        text = example.get("text", "")
        expected_text = render_example(
            template, tool, prompt, task["expected_command"], system_prompt
        )
        if text != expected_text:
            errors.append(f"{label_id}: text differs from a fresh template render")
        if EXPECTED_PREFIX not in text:
            errors.append(f"{label_id}: missing native assistant/<think> prefix")

        assistant_part = text.rsplit("<|im_start|>assistant\n", 1)[-1]
        functions = FUNCTION_RE.findall(assistant_part)
        if functions != [tool["function"]["name"]]:
            errors.append(
                f"{label_id}: expected one {tool['function']['name']} function, "
                f"got {functions}"
            )
        parameters = PARAMETER_RE.findall(assistant_part)
        if len(parameters) != 1:
            errors.append(f"{label_id}: expected one command parameter, got {len(parameters)}")
        else:
            command = parameters[0][1].strip()
            if command != task["expected_command"]:
                errors.append(
                    f"{label_id}: command {command!r} != expected {task['expected_command']!r}"
                )
            if not command.startswith("glab "):
                errors.append(f"{label_id}: command is not a glab invocation")
            if MUTATING_RE.search(command):
                errors.append(f"{label_id}: command looks mutating: {command!r}")
            for pattern in task["forbidden_patterns"]:
                if re.search(pattern, command):
                    errors.append(f"{label_id}: forbidden pattern {pattern!r} in command")

        if example.get("target_format") != "qwen3_5_native_xml":
            errors.append(f"{label_id}: unexpected target_format")
        expected_split = "failure" if task_id in failure_ids else "control"
        if example.get("split") != expected_split:
            errors.append(f"{label_id}: split should be {expected_split}")

    for task_id in task_by_id:
        expected_count = (
            FAILURE_PARAPHRASES if task_id in failure_ids else CONTROL_PARAPHRASES
        )
        actual = per_task.get(task_id, 0)
        if actual != expected_count:
            errors.append(
                f"{label}: {task_id}: expected {expected_count} examples, got {actual}"
            )

    if len(examples) != manifest["counts"]["examples"]:
        errors.append(f"{label}: manifest example count does not match the JSONL file")

    return errors


def validate_url_family(label: str, rel_dir: str, shape: str, lang: str) -> list[str]:
    """Validate one URL-entity dataset against the frozen spec and template."""
    data_dir = DATA_ROOT / rel_dir
    output_path = data_dir / "sft.jsonl"
    heldout_path = data_dir / f"heldout.{lang}.jsonl"
    manifest_path = data_dir / "dataset_manifest.json"
    errors: list[str] = []
    if not output_path.is_file():
        return [f"{label}: missing {output_path}"]
    if not manifest_path.is_file():
        return [f"{label}: missing {manifest_path}"]

    config = load_config()
    if shape == "shell":
        tool, system_prompt = shell_assets()
    else:
        tool, system_prompt = build_tool(config), None
    template = make_environment().from_string(
        (EVAL_ROOT / "docs" / "chat_template.jinja").read_text()
    )
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("family") != "url":
        errors.append(f"{label}: manifest family is {manifest.get('family')!r}")
    if manifest.get("lang") != lang:
        errors.append(f"{label}: manifest lang is {manifest.get('lang')!r}")
    if manifest.get("shape") != shape:
        errors.append(f"{label}: manifest shape is {manifest.get('shape')!r}")

    expected_hashes = {
        "slots.jsonl": URL_FAMILY_PATH,
        "phrasings.json": URL_PHRASINGS_PATH,
        "chat_template.jinja": EVAL_ROOT / "docs" / "chat_template.jinja",
        "build_dataset.py": ROOT / "train" / "build_dataset.py",
    }
    if shape == "glab":
        expected_hashes["config.yaml"] = EVAL_ROOT / "config.yaml"
    else:
        expected_hashes.update(
            {name: OPENCODE_DIR / name for name in SHELL_SOURCE_NAMES}
        )
    ru_path = EVAL_ROOT / "tasks.ru.jsonl"
    if ru_path.is_file():
        expected_hashes["tasks.ru.jsonl"] = ru_path
    for name, path in expected_hashes.items():
        if manifest["source_sha256"].get(name) != sha256_file(path):
            errors.append(f"{label}: manifest source hash stale for {name}")
    tool_sha = (
        canonical_tool_sha(tool) if shape == "shell" else tool_schema_sha256(config)
    )
    if manifest["tool_schema_sha256"] != tool_sha:
        errors.append(f"{label}: manifest tool schema hash does not match the tool")

    expected = url_family_rows(lang, shape)
    expected_train = {row["id"]: row for row in expected if row["split"] == "train"}
    expected_holdout = {row["id"]: row for row in expected if row["split"] == "holdout"}
    original_prompts = eval_prompts()

    actual: dict[str, dict[str, Any]] = {}
    with output_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row_id = row.get("id")
            if row_id in actual:
                errors.append(f"{label}: duplicate id {row_id!r}")
            actual[row_id] = row
    missing = sorted(set(expected_train) - set(actual))
    extra = sorted(set(actual) - set(expected_train))
    if missing:
        errors.append(f"{label}: missing train rows: {missing[:5]}")
    if extra:
        errors.append(f"{label}: unexpected rows: {extra[:5]}")

    seen_prompts: set[str] = set()
    for row_id, row in actual.items():
        label_id = f"{label}: {row_id}"
        expected_row = expected_train.get(row_id)
        if expected_row is None:
            continue
        if row.get("prompt") != expected_row["prompt"]:
            errors.append(f"{label_id}: prompt differs from the spec")
        if row.get("expected_command") != expected_row["expected_command"]:
            errors.append(f"{label_id}: command differs from the spec")
        prompt = row["prompt"]
        if prompt in original_prompts:
            errors.append(f"{label_id}: prompt is an original eval prompt")
        if prompt in seen_prompts:
            errors.append(f"{label_id}: duplicate prompt")
        seen_prompts.add(prompt)
        if row.get("shape", "glab") != shape:
            errors.append(f"{label_id}: row shape is {row.get('shape')!r}")
        command = row["expected_command"]
        if not command.startswith("glab "):
            errors.append(f"{label_id}: command is not a glab invocation")
        if command.startswith("glab api") and "work_items" in command:
            errors.append(f"{label_id}: api command uses the work_items endpoint")
        if "graphql" in command:
            errors.append(f"{label_id}: graphql targets are out of scope")
        if MUTATING_RE.search(command):
            errors.append(f"{label_id}: command looks mutating: {command!r}")
        text = row.get("text", "")
        expected_text = render_example(template, tool, prompt, command, system_prompt)
        if text != expected_text:
            errors.append(f"{label_id}: text differs from a fresh template render")
        if EXPECTED_PREFIX not in text:
            errors.append(f"{label_id}: missing native assistant/<think> prefix")

    if not heldout_path.is_file():
        errors.append(f"{label}: missing {heldout_path}")
    else:
        heldout = [
            json.loads(line)
            for line in heldout_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if {row["id"] for row in heldout} != set(expected_holdout):
            errors.append(f"{label}: held-out ids differ from the spec")
        leaked = sorted({row["prompt"] for row in heldout} & seen_prompts)
        if leaked:
            errors.append(f"{label}: held-out prompts leaked into training: {leaked[:3]}")

    if manifest["counts"]["examples"] != len(actual):
        errors.append(f"{label}: manifest example count does not match the JSONL file")
    if manifest["counts"]["held_out"] != len(expected_holdout):
        errors.append(f"{label}: manifest held-out count does not match the spec")
    return errors


def validate_ext_family(label: str, rel_dir: str, shape: str, lang: str) -> list[str]:
    """Validate one ext dataset against the spec, template and shell contract."""
    data_dir = DATA_ROOT / rel_dir
    output_path = data_dir / "sft.jsonl"
    heldout_path = data_dir / f"heldout.{lang}.jsonl"
    manifest_path = data_dir / "dataset_manifest.json"
    if not output_path.is_file():
        return [f"{label}: missing {output_path}"]
    if not manifest_path.is_file():
        return [f"{label}: missing {manifest_path}"]
    errors: list[str] = []
    config = load_config()
    tool, system_prompt = shell_assets()
    template = make_environment().from_string(
        (EVAL_ROOT / "docs" / "chat_template.jinja").read_text()
    )
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("family") != "ext":
        errors.append(f"{label}: manifest family is {manifest.get('family')!r}")
    if manifest.get("lang") != lang:
        errors.append(f"{label}: manifest lang is {manifest.get('lang')!r}")
    if manifest.get("shape") != shape:
        errors.append(f"{label}: manifest shape is {manifest.get('shape')!r}")

    expected_hashes = {
        "tasks.ext.jsonl": DATA_ROOT / "ext" / "spec" / "tasks.ext.jsonl",
        "chat_template.jinja": EVAL_ROOT / "docs" / "chat_template.jinja",
        "build_dataset.py": ROOT / "train" / "build_dataset.py",
    }
    expected_hashes.update({name: OPENCODE_DIR / name for name in SHELL_SOURCE_NAMES})
    for name in manifest["source_sha256"]:
        if name.startswith("help-"):
            expected_hashes[name] = EVAL_ROOT / "docs" / name
    if (EVAL_ROOT / "tasks.ru.jsonl").is_file():
        expected_hashes["tasks.ru.jsonl"] = EVAL_ROOT / "tasks.ru.jsonl"
    for name, path in expected_hashes.items():
        if manifest["source_sha256"].get(name) != sha256_file(path):
            errors.append(f"{label}: manifest source hash stale for {name}")
    if manifest["tool_schema_sha256"] != canonical_tool_sha(tool):
        errors.append(f"{label}: manifest tool schema hash does not match the tool")

    expected = ext_rows(lang, shape)
    expected_train = {row["id"]: row for row in expected if row["split"] == "train"}
    expected_holdout = {row["id"]: row for row in expected if row["split"] == "holdout"}
    original_prompts = eval_prompts()

    actual: dict[str, dict[str, Any]] = {}
    with output_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["id"] in actual:
                errors.append(f"{label}: duplicate id {row['id']!r}")
            actual[row["id"]] = row
    missing = sorted(set(expected_train) - set(actual))
    extra = sorted(set(actual) - set(expected_train))
    if missing:
        errors.append(f"{label}: missing train rows: {missing[:5]}")
    if extra:
        errors.append(f"{label}: unexpected rows: {extra[:5]}")

    seen_prompts: set[str] = set()
    for row_id, row in actual.items():
        label_id = f"{label}: {row_id}"
        expected_row = expected_train.get(row_id)
        if expected_row is None:
            continue
        if row.get("prompt") != expected_row["prompt"]:
            errors.append(f"{label_id}: prompt differs from the spec")
        if row.get("expected_command") != expected_row["expected_command"]:
            errors.append(f"{label_id}: command differs from the spec")
        prompt = row["prompt"]
        if prompt in original_prompts:
            errors.append(f"{label_id}: prompt is an original eval prompt")
        if prompt in seen_prompts:
            errors.append(f"{label_id}: duplicate prompt")
        seen_prompts.add(prompt)
        if row.get("shape") != "shell":
            errors.append(f"{label_id}: row shape is {row.get('shape')!r}")
        command = row["expected_command"]
        if not command.startswith("glab "):
            errors.append(f"{label_id}: command is not a glab invocation")
        if command.startswith("glab api") and "work_items" in command:
            errors.append(f"{label_id}: api command uses the work_items endpoint")
        if "graphql" in command:
            errors.append(f"{label_id}: graphql targets are out of scope")
        if MUTATING_RE.search(command):
            errors.append(f"{label_id}: command looks mutating: {command!r}")
        text = row.get("text", "")
        expected_text = render_example(template, tool, prompt, command, system_prompt)
        if text != expected_text:
            errors.append(f"{label_id}: text differs from a fresh template render")
        if EXPECTED_PREFIX not in text:
            errors.append(f"{label_id}: missing native assistant/<think> prefix")

    if not heldout_path.is_file():
        errors.append(f"{label}: missing {heldout_path}")
    else:
        heldout = [
            json.loads(line)
            for line in heldout_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if {row["id"] for row in heldout} != set(expected_holdout):
            errors.append(f"{label}: held-out ids differ from the spec")
        leaked = sorted({row["prompt"] for row in heldout} & seen_prompts)
        if leaked:
            errors.append(f"{label}: held-out prompts leaked into training: {leaked[:3]}")

    if manifest["counts"]["examples"] != len(actual):
        errors.append(f"{label}: manifest example count does not match the JSONL file")
    if manifest["counts"]["held_out"] != len(expected_holdout):
        errors.append(f"{label}: manifest held-out count does not match the spec")
    return errors


def cross_language_check(datasets: tuple[tuple[str, str, str, str], ...], shape: str) -> list[str]:
    errors: list[str] = []
    prompts: dict[str, set[str]] = {}
    for label, rel_dir, dataset_shape, lang in datasets:
        if dataset_shape != shape:
            continue
        path = DATA_ROOT / rel_dir / "sft.jsonl"
        if not path.is_file():
            errors.append(f"{label}: missing {path}")
            continue
        prompts[lang] = {
            json.loads(line)["prompt"]
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    if len(prompts) == 2:
        overlap = prompts["en"] & prompts["ru"]
        if overlap:
            errors.append(f"{shape} cross-language duplicate prompts: {sorted(overlap)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lang",
        choices=["all", "en", "ru"],
        default="all",
        help="Validate one language or both (default: all)",
    )
    parser.add_argument(
        "--shape",
        choices=["all", "glab", "shell"],
        default="all",
        help="Validate one tool shape or both (default: all)",
    )
    parser.add_argument(
        "--family",
        choices=["all", "tasks", "url", "ext"],
        default="all",
        help="Validate the task, URL or ext family, or all (default: all)",
    )
    args = parser.parse_args()

    tasks_selected = [
        item
        for item in DATASETS
        if (args.lang == "all" or item[3] == args.lang)
        and (args.shape == "all" or item[2] == args.shape)
        and args.family in ("all", "tasks")
    ]
    url_selected = [
        item
        for item in URL_DATASETS
        if (args.lang == "all" or item[3] == args.lang)
        and (args.shape == "all" or item[2] == args.shape)
        and args.family in ("all", "url")
    ]
    ext_selected = [
        item
        for item in EXT_DATASETS
        if (args.lang == "all" or item[3] == args.lang)
        and (args.shape == "all" or item[2] == args.shape)
        and args.family in ("all", "ext")
    ]
    errors: list[str] = []
    total = 0
    for label, rel_dir, shape, lang in tasks_selected:
        dataset_errors = validate(label, rel_dir, shape, lang)
        errors.extend(dataset_errors)
        if not dataset_errors:
            path = DATA_ROOT / rel_dir / "sft.jsonl"
            count = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
            total += count
            print(f"OK {label}: {count} examples")
    for label, rel_dir, shape, lang in url_selected:
        dataset_errors = validate_url_family(label, rel_dir, shape, lang)
        errors.extend(dataset_errors)
        if not dataset_errors:
            path = DATA_ROOT / rel_dir / "sft.jsonl"
            count = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
            total += count
            print(f"OK {label}: {count} examples")
    for label, rel_dir, shape, lang in ext_selected:
        dataset_errors = validate_ext_family(label, rel_dir, shape, lang)
        errors.extend(dataset_errors)
        if not dataset_errors:
            path = DATA_ROOT / rel_dir / "sft.jsonl"
            count = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
            total += count
            print(f"OK {label}: {count} examples")
    selected = tasks_selected + url_selected + ext_selected
    for shape in sorted({item[2] for item in selected}):
        if {item[3] for item in selected if item[2] == shape} == {"en", "ru"}:
            errors.extend(cross_language_check(tuple(selected), shape))

    if errors:
        print(f"FAIL {len(errors)} problem(s):")
        for error in errors[:40]:
            print(f"  - {error}")
        if len(errors) > 40:
            print(f"  ... and {len(errors) - 40} more")
        return 1

    print(f"OK {total} examples across {len(selected)} datasets")
    print("  eval prompt collisions: 0")
    print("  native XML targets: 100%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
