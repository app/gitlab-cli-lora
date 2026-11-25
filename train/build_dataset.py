"""Build native-XML glab SFT data from the frozen evaluation artifacts.

Two shapes share the same paraphrases and targets:

``glab``  -- the original single-purpose ``run_glab_command`` contract.
``shell`` -- the frozen OpenCode serving contract (system prompt and ``shell``
tool captured from live OpenCode v2.4.1, see ``train/data/contracts/opencode/README.md``).

Two families:

``tasks`` -- the 38 eval tasks and their paraphrases (default).
``url``   -- the URL-entity family from ``train/data/url/spec/slots.jsonl``: any
GitLab issue/work-item URL maps to ``glab issue view <url>``, while REST
phrasing maps to the issues API. Project names deliberately collide with the
entity vocabulary (``issue``, ``work-items``) so the rule is structural.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jinja2
from jinja2.ext import Extension, loopcontrols
from jinja2.sandbox import ImmutableSandboxedEnvironment

ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "glab-eval"
DATA_ROOT = ROOT / "train" / "data"
sys.path.insert(0, str(EVAL_ROOT))

from common import (  # noqa: E402
    PARAMETER_RE,
    build_tool,
    load_config,
    load_tasks,
    sha256_bytes,
    sha256_file,
    tool_schema_sha256,
)

FAILURE_PARAPHRASES = 6
CONTROL_PARAPHRASES = 3
# Layout: train/data/<family>/<shape>/<lang>/{sft.jsonl,dataset_manifest.json};
# specs live next to their family, the serving contract under contracts/.
OUTPUT_NAME = "sft.jsonl"
MANIFEST_NAME = "dataset_manifest.json"
OPENCODE_DIR = DATA_ROOT / "contracts" / "opencode"
TASKS_SPEC_DIR = DATA_ROOT / "tasks" / "spec"
URL_SPEC_DIR = DATA_ROOT / "url" / "spec"
SHELL_SOURCE_NAMES = (
    "shell-tool.json",
    "system-prompt.txt",
    "system-prompt.raw.txt",
    "capture-request.json",
)
URL_FAMILY_PATH = URL_SPEC_DIR / "slots.jsonl"
URL_PHRASINGS_PATH = URL_SPEC_DIR / "phrasings.json"
EXT_SPEC_PATH = DATA_ROOT / "ext" / "spec" / "tasks.ext.jsonl"
URL_SOURCE_URL = (
    "https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/issue/view.md"
)
URL_SOURCE_EXCERPT = "You can use a full GitLab URL instead of an ID."


class GenerationBlock(Extension):
    """Minimal equivalent of transformers' generation block marker."""

    tags = {"generation"}

    def parse(self, parser: jinja2.parser.Parser) -> jinja2.nodes.CallBlock:
        lineno = next(parser.stream).lineno
        body = parser.parse_statements(["name:endgeneration"], drop_needle=True)
        return jinja2.nodes.CallBlock(self.call_method("_render"), [], [], body).set_lineno(
            lineno
        )

    def _render(self, caller: Any) -> str:
        return caller()


def raise_exception(message: str) -> None:
    raise jinja2.exceptions.TemplateError(message)


def tojson(
    value: Any,
    ensure_ascii: bool = False,
    indent: int | None = None,
    separators: tuple[str, str] | None = None,
    sort_keys: bool = False,
) -> str:
    return json.dumps(
        value,
        ensure_ascii=ensure_ascii,
        indent=indent,
        separators=separators,
        sort_keys=sort_keys,
    )


def make_environment() -> jinja2.Environment:
    """Match transformers 4.57.6 apply_chat_template's Jinja environment."""
    env = ImmutableSandboxedEnvironment(
        trim_blocks=True,
        lstrip_blocks=True,
        extensions=[GenerationBlock, loopcontrols],
    )
    env.filters["tojson"] = tojson
    env.globals["raise_exception"] = raise_exception
    return env


def latest_handoff_path() -> Path:
    index = json.loads((EVAL_ROOT / "results" / "index.json").read_text())
    run_id = index["suites"]["baseline"]["runs"][0]["run_id"]
    path = EVAL_ROOT / "results" / run_id / "training_handoff.json"
    if not path.is_file():
        raise FileNotFoundError(f"missing training handoff: {path}")
    return path


def load_paraphrases(path: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            item = json.loads(line)
            task_id = item["task_id"]
            if task_id in result:
                raise ValueError(f"duplicate paraphrase task_id {task_id!r} on line {line_number}")
            result[task_id] = list(item["paraphrases"])
    return result


def paraphrase_path(lang: str) -> Path:
    return TASKS_SPEC_DIR / f"paraphrases.{lang}.jsonl"


def family_out_dir(family: str, shape: str, lang: str) -> Path:
    contract = "shell" if shape == "shell" else "glab"
    return DATA_ROOT / family / contract / lang


def shell_assets() -> tuple[dict[str, Any], str]:
    """Frozen OpenCode serving contract: the `shell` tool object and system prompt."""
    tool = json.loads((OPENCODE_DIR / "shell-tool.json").read_text(encoding="utf-8"))
    system_prompt = (OPENCODE_DIR / "system-prompt.txt").read_text(encoding="utf-8")
    return tool, system_prompt


def canonical_tool_sha(tool: dict[str, Any]) -> str:
    """Same serialization as common.tool_schema_sha256."""
    return sha256_bytes(
        json.dumps(
            tool, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    )


def render_example(
    template: jinja2.Template,
    tool: dict[str, Any],
    prompt: str,
    command: str,
    system_prompt: str | None = None,
) -> str:
    """Render a full conversation: prompt plus an empty-think native tool call."""
    messages: list[dict[str, Any]] = []
    if system_prompt is not None:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    messages.append(
        {
            "role": "assistant",
            "reasoning_content": "",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_glab",
                    "type": "function",
                    "function": {
                        "name": tool["function"]["name"],
                        "arguments": {"command": command},
                    },
                }
            ],
        }
    )
    # enable_thinking and preserve_thinking are intentionally undefined.
    # That makes the template emit the same <think>\n prefix as eval and
    # render the assistant answer inside the generation block.
    return template.render(
        messages=messages,
        tools=[tool],
        reasoning_effort="low",
        add_generation_prompt=False,
    )


def url_for(slot: dict[str, Any]) -> str:
    return (
        f"https://gitlab.com/{slot['group']}/{slot['project']}"
        f"/-/{slot['url_form']}/{slot['iid']}"
    )


def canonical_url_command(slot: dict[str, Any], phrasing: dict[str, str]) -> str:
    """Canonical reader for a GitLab issue/work-item URL family slot."""
    if phrasing["kind"] == "url":
        return f"glab issue view {url_for(slot)}"
    if phrasing["kind"] == "api":
        project = f"{slot['group']}%2F{slot['project']}"
        return f'glab api "projects/{project}/issues/{slot["iid"]}"'
    raise ValueError(f"unknown URL phrasing kind {phrasing['kind']!r}")


def url_family_rows(lang: str, shape: str) -> list[dict[str, Any]]:
    """Cross the slot spec with the phrasing table; one row per train pair."""
    slots = [
        json.loads(line)
        for line in URL_FAMILY_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    phrasings = json.loads(URL_PHRASINGS_PATH.read_text(encoding="utf-8"))[lang]
    shape_tag = "shell-url" if shape == "shell" else "url"
    id_prefix = shape_tag + ("-ru" if lang == "ru" else "")
    rows: list[dict[str, Any]] = []
    for slot in slots:
        for phrasing in phrasings:
            # The API phrasing names the project and iid, not a URL, so the two
            # URL forms of one slot would produce identical prompts; keep one.
            if phrasing["kind"] == "api" and slot["url_form"] != "work_items":
                continue
            prompt = phrasing["template"].format(
                url=url_for(slot),
                iid=slot["iid"],
                group=slot["group"],
                project=slot["project"],
            )
            split = (
                "train"
                if slot["split"] == "train" and phrasing["split"] == "train"
                else "holdout"
            )
            rows.append(
                {
                    "id": (
                        f"{id_prefix}-{slot['group']}-{slot['project']}"
                        f"-{slot['url_form']}-{slot['iid']}-{phrasing['id']}"
                    ),
                    "family": "url",
                    "task_id": f"url-{phrasing['id']}",
                    "split": split,
                    "category": "url",
                    "group": slot["group"],
                    "project": slot["project"],
                    "iid": slot["iid"],
                    "url_form": slot["url_form"],
                    "phrasing_id": phrasing["id"],
                    "kind": phrasing["kind"],
                    "prompt": prompt,
                    "expected_command": canonical_url_command(slot, phrasing),
                    "target_format": "qwen3_5_native_xml",
                    "source_kind": "docs",
                    "source_url": URL_SOURCE_URL,
                    "source_excerpt": URL_SOURCE_EXCERPT,
                }
            )
    return rows


def load_ext_tasks() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in EXT_SPEC_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def ext_rows(lang: str, shape: str) -> list[dict[str, Any]]:
    """Cross the ext task spec with the language prompts; shell shape only."""
    if shape != "shell":
        raise SystemExit("the ext family is shell-shape only (owner decision)")
    sources = json.loads((EVAL_ROOT / "docs" / "sources.json").read_text(encoding="utf-8"))
    url_by_file = {item["file"]: item["url"] for item in sources["sources"]}
    id_prefix = "ext-" if lang == "en" else "ext-ru-"
    rows: list[dict[str, Any]] = []
    for task in load_ext_tasks():
        prompts = task["prompts"][lang]
        for index, prompt in enumerate(prompts, 1):
            rows.append(
                {
                    "id": f"{id_prefix}{task['id']}-p{index}",
                    "family": "ext",
                    "task_id": task["id"],
                    "split": task["split"],
                    "category": task["category"],
                    "prompt": prompt,
                    "expected_command": task["expected_command"],
                    "target_format": "qwen3_5_native_xml",
                    "source_kind": "help",
                    "source_url": url_by_file.get(task["source_help"], ""),
                    "source_excerpt": task["source_help"],
                }
            )
    return rows


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_url_family(lang: str, shape: str) -> None:
    """Render the URL-entity family into train/data/url{,-shell}/<lang>."""
    config = load_config()
    if shape == "shell":
        tool, system_prompt = shell_assets()
    else:
        tool, system_prompt = build_tool(config), None
    template = make_environment().from_string(
        (EVAL_ROOT / "docs" / "chat_template.jinja").read_text(encoding="utf-8")
    )
    eval_prompts = {task["prompt"] for task in load_tasks()}
    ru_tasks_path = EVAL_ROOT / "tasks.ru.jsonl"
    if ru_tasks_path.is_file():
        eval_prompts |= {task["prompt"] for task in load_tasks(ru_tasks_path)}

    train_rows: list[dict[str, Any]] = []
    holdout_rows: list[dict[str, Any]] = []
    for row in url_family_rows(lang, shape):
        if row["prompt"] in eval_prompts:
            raise ValueError(f"{row['id']}: prompt collides with an eval prompt")
        text = render_example(
            template, tool, row["prompt"], row["expected_command"], system_prompt
        )
        assistant_part = text.rsplit("<|im_start|>assistant\n", 1)[-1]
        parameters = PARAMETER_RE.findall(assistant_part)
        if (
            len(parameters) != 1
            or parameters[0][0] != "command"
            or parameters[0][1].strip() != row["expected_command"]
        ):
            raise ValueError(f"{row['id']}: rendered target command mismatch")
        for marker in (
            "<|im_start|>assistant\n<think>\n\n</think>\n\n<tool_call>\n",
            f"<function={tool['function']['name']}>\n",
            "</function>\n</tool_call><|im_end|>",
        ):
            if marker not in text:
                raise ValueError(f"{row['id']}: rendered text lacks {marker!r}")
        row = dict(row)
        row["text"] = text
        if shape == "shell":
            row["shape"] = "shell"
        (train_rows if row["split"] == "train" else holdout_rows).append(row)

    out_dir = family_out_dir("url", shape, lang)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / OUTPUT_NAME
    heldout_path = out_dir / f"heldout.{lang}.jsonl"
    manifest_path = out_dir / MANIFEST_NAME
    write_rows(output_path, train_rows)
    write_rows(heldout_path, holdout_rows)

    source_paths = {
        "slots.jsonl": URL_FAMILY_PATH,
        "phrasings.json": URL_PHRASINGS_PATH,
        "chat_template.jinja": EVAL_ROOT / "docs" / "chat_template.jinja",
        "build_dataset.py": ROOT / "train" / "build_dataset.py",
    }
    if shape == "glab":
        source_paths["config.yaml"] = EVAL_ROOT / "config.yaml"
    else:
        source_paths.update({name: OPENCODE_DIR / name for name in SHELL_SOURCE_NAMES})
    if ru_tasks_path.is_file():
        source_paths["tasks.ru.jsonl"] = ru_tasks_path
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "family": "url",
        "lang": lang,
        "shape": shape,
        "target_format": "qwen3_5_native_xml",
        "reasoning_effort": config["generation"]["reasoning_effort"],
        "source_sha256": {
            name: sha256_file(path) for name, path in source_paths.items()
        },
        "tool_schema_sha256": (
            canonical_tool_sha(tool)
            if shape == "shell"
            else tool_schema_sha256(config)
        ),
        "template": {
            "enable_thinking": "undefined",
            "preserve_thinking": "undefined",
            "add_generation_prompt": False,
            "jinja2_version": jinja2.__version__,
        },
        "counts": {
            "examples": len(train_rows),
            "held_out": len(holdout_rows),
            "by_project": {
                key: sum(
                    1
                    for row in train_rows
                    if f"{row['group']}/{row['project']}" == key
                )
                for key in sorted(
                    {f"{row['group']}/{row['project']}" for row in train_rows}
                )
            },
            "by_phrasing": {
                key: sum(1 for row in train_rows if row["phrasing_id"] == key)
                for key in sorted({row["phrasing_id"] for row in train_rows})
            },
        },
        "held_out": {
            "projects": sorted(
                {
                    f"{row['group']}/{row['project']}"
                    for row in holdout_rows
                    if row["split"] == "holdout"
                }
            ),
            "phrasings": sorted(
                {
                    row["phrasing_id"]
                    for row in holdout_rows
                }
            ),
            "eval_prompt_count": len(eval_prompts),
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {len(train_rows)} examples to {output_path.relative_to(ROOT)} "
        f"(family=url, shape={shape}, {len(holdout_rows)} held out)"
    )
    print(f"wrote manifest to {manifest_path.relative_to(ROOT)}")


def build_ext(lang: str, shape: str) -> None:
    """Render the lean ext family into train/data/ext/shell/<lang>."""
    config = load_config()
    if shape != "shell":
        raise SystemExit("the ext family is shell-shape only (owner decision)")
    tool, system_prompt = shell_assets()
    template = make_environment().from_string(
        (EVAL_ROOT / "docs" / "chat_template.jinja").read_text(encoding="utf-8")
    )
    eval_prompts = {task["prompt"] for task in load_tasks()}
    ru_tasks_path = EVAL_ROOT / "tasks.ru.jsonl"
    if ru_tasks_path.is_file():
        eval_prompts |= {task["prompt"] for task in load_tasks(ru_tasks_path)}

    train_rows: list[dict[str, Any]] = []
    holdout_rows: list[dict[str, Any]] = []
    for row in ext_rows(lang, shape):
        if row["prompt"] in eval_prompts:
            raise ValueError(f"{row['id']}: prompt collides with an eval prompt")
        text = render_example(
            template, tool, row["prompt"], row["expected_command"], system_prompt
        )
        assistant_part = text.rsplit("<|im_start|>assistant\n", 1)[-1]
        parameters = PARAMETER_RE.findall(assistant_part)
        if (
            len(parameters) != 1
            or parameters[0][0] != "command"
            or parameters[0][1].strip() != row["expected_command"]
        ):
            raise ValueError(f"{row['id']}: rendered target command mismatch")
        for marker in (
            "<|im_start|>assistant\n<think>\n\n</think>\n\n<tool_call>\n",
            f"<function={tool['function']['name']}>\n",
            "</function>\n</tool_call><|im_end|>",
        ):
            if marker not in text:
                raise ValueError(f"{row['id']}: rendered text lacks {marker!r}")
        row = dict(row)
        row["text"] = text
        row["shape"] = "shell"
        (train_rows if row["split"] == "train" else holdout_rows).append(row)

    out_dir = family_out_dir("ext", shape, lang)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / OUTPUT_NAME
    heldout_path = out_dir / f"heldout.{lang}.jsonl"
    manifest_path = out_dir / MANIFEST_NAME
    write_rows(output_path, train_rows)
    write_rows(heldout_path, holdout_rows)

    help_files = sorted({task["source_help"] for task in load_ext_tasks()})
    source_paths = {
        "tasks.ext.jsonl": EXT_SPEC_PATH,
        "chat_template.jinja": EVAL_ROOT / "docs" / "chat_template.jinja",
        "build_dataset.py": ROOT / "train" / "build_dataset.py",
    }
    source_paths.update({name: OPENCODE_DIR / name for name in SHELL_SOURCE_NAMES})
    for name in help_files:
        source_paths[name] = EVAL_ROOT / "docs" / name
    if ru_tasks_path.is_file():
        source_paths["tasks.ru.jsonl"] = ru_tasks_path
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "family": "ext",
        "lang": lang,
        "shape": shape,
        "target_format": "qwen3_5_native_xml",
        "reasoning_effort": config["generation"]["reasoning_effort"],
        "source_sha256": {
            name: sha256_file(path) for name, path in source_paths.items()
        },
        "tool_schema_sha256": canonical_tool_sha(tool),
        "template": {
            "enable_thinking": "undefined",
            "preserve_thinking": "undefined",
            "add_generation_prompt": False,
            "jinja2_version": jinja2.__version__,
        },
        "counts": {
            "examples": len(train_rows),
            "held_out": len(holdout_rows),
            "by_category": {
                key: sum(1 for row in train_rows if row["category"] == key)
                for key in sorted({row["category"] for row in train_rows})
            },
        },
        "held_out": {
            "tasks": sorted({row["task_id"] for row in holdout_rows}),
            "ids": sorted(row["id"] for row in holdout_rows),
            "eval_prompt_count": len(eval_prompts),
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {len(train_rows)} examples to {output_path.relative_to(ROOT)} "
        f"(family=ext, shape={shape}, {len(holdout_rows)} held out)"
    )
    print(f"wrote manifest to {manifest_path.relative_to(ROOT)}")


def build() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lang",
        choices=["en", "ru"],
        default="en",
        help="Language directory under train/data (default: en)",
    )
    parser.add_argument(
        "--shape",
        choices=["glab", "shell"],
        default="glab",
        help="Tool contract: run_glab_command (default) or the frozen OpenCode shell",
    )
    parser.add_argument(
        "--family",
        choices=["tasks", "url", "ext"],
        default="tasks",
        help="Dataset family: eval tasks (default), URL-entity slots or ext tasks",
    )
    parser.add_argument(
        "--handoff",
        type=Path,
        default=None,
        help="Training handoff JSON (default: latest baseline run from index.json)",
    )
    args = parser.parse_args()

    if args.family == "url":
        build_url_family(args.lang, args.shape)
        return
    if args.family == "ext":
        build_ext(args.lang, args.shape)
        return

    paraphrase_file = paraphrase_path(args.lang)
    out_dir = family_out_dir("tasks", args.shape, args.lang)
    output_path = out_dir / OUTPUT_NAME
    manifest_path = out_dir / MANIFEST_NAME
    # English ids stay bare so the frozen dataset remains byte-identical;
    # other languages are prefixed so ids are unique across the concatenated mix.
    # Shell-shape ids always carry the shape tag to stay unique against glab ids.
    if args.shape == "shell":
        id_prefix = "shell-" if args.lang == "en" else f"shell-{args.lang}-"
    else:
        id_prefix = "" if args.lang == "en" else f"{args.lang}-"

    config = load_config()
    tasks = load_tasks()
    # Check against both frozen eval sets: no training prompt may equal any eval
    # prompt, in either language.
    eval_prompts = {task["prompt"] for task in tasks}
    ru_tasks_path = EVAL_ROOT / "tasks.ru.jsonl"
    if ru_tasks_path.is_file():
        eval_prompts |= {task["prompt"] for task in load_tasks(ru_tasks_path)}
    handoff_path = args.handoff or latest_handoff_path()
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    paraphrases = load_paraphrases(paraphrase_file)

    task_by_id = {task["id"]: task for task in tasks}
    if len(task_by_id) != len(tasks):
        raise ValueError("tasks.jsonl contains duplicate ids")

    failure_ids = set(handoff["stable_failure_task_ids"])
    control_ids = set(handoff["control_task_ids"])
    if failure_ids & control_ids:
        raise ValueError("failure and control task ids overlap")
    if failure_ids | control_ids != set(task_by_id):
        raise ValueError("handoff does not cover all eval tasks")

    if args.shape == "shell":
        tool, system_prompt = shell_assets()
    else:
        tool, system_prompt = build_tool(config), None
    template = make_environment().from_string(
        (EVAL_ROOT / "docs" / "chat_template.jinja").read_text(encoding="utf-8")
    )

    examples: list[dict[str, Any]] = []
    by_task: dict[str, int] = {}
    for task_id in sorted(task_by_id):
        task = task_by_id[task_id]
        expected_count = (
            FAILURE_PARAPHRASES if task_id in failure_ids else CONTROL_PARAPHRASES
        )
        prompts = paraphrases.get(task_id, [])
        if len(prompts) != expected_count:
            raise ValueError(
                f"{task_id}: expected {expected_count} paraphrases, got {len(prompts)}"
            )
        for index, prompt in enumerate(prompts):
            if prompt == task["prompt"]:
                raise ValueError(f"{task_id}: paraphrase {index} equals the eval prompt")
            text = render_example(
                template, tool, prompt, task["expected_command"], system_prompt
            )
            assistant_part = text.rsplit("<|im_start|>assistant\n", 1)[-1]
            parameters = PARAMETER_RE.findall(assistant_part)
            if (
                len(parameters) != 1
                or parameters[0][0] != "command"
                or parameters[0][1].strip() != task["expected_command"]
            ):
                raise ValueError(f"{task_id}: rendered target command mismatch")
            for marker in (
                "<|im_start|>assistant\n<think>\n\n</think>\n\n<tool_call>\n",
                f"<function={tool['function']['name']}>\n",
                "</function>\n</tool_call><|im_end|>",
            ):
                if marker not in text:
                    raise ValueError(f"{task_id}: rendered text lacks {marker!r}")
            example = {
                "id": f"{id_prefix}{task_id}-p{index + 1}",
                "task_id": task_id,
                "split": "failure" if task_id in failure_ids else "control",
                "category": task["category"],
                "prompt": prompt,
                "expected_command": task["expected_command"],
                "target_format": "qwen3_5_native_xml",
                "source_kind": task["source_kind"],
                "source_url": task["source_url"],
                "source_excerpt": task["source_excerpt"],
                "text": text,
            }
            if args.shape == "shell":
                example["shape"] = "shell"
            examples.append(example)
        by_task[task_id] = len(prompts)

    collisions = sorted(
        example["id"]
        for example in examples
        if example["prompt"] in eval_prompts
    )
    if collisions:
        raise ValueError(f"training prompts collide with eval prompts: {collisions}")

    source_paths = {
        "config.yaml": EVAL_ROOT / "config.yaml",
        "tasks.jsonl": EVAL_ROOT / "tasks.jsonl",
        "chat_template.jinja": EVAL_ROOT / "docs" / "chat_template.jinja",
        "training_handoff.json": handoff_path,
        "paraphrases.jsonl": paraphrase_file,
        "build_dataset.py": ROOT / "train" / "build_dataset.py",
    }
    if ru_tasks_path.is_file():
        source_paths["tasks.ru.jsonl"] = ru_tasks_path
    if args.shape == "shell":
        source_paths.update({name: OPENCODE_DIR / name for name in SHELL_SOURCE_NAMES})
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "lang": args.lang,
        "shape": args.shape,
        "target_format": "qwen3_5_native_xml",
        "reasoning_effort": config["generation"]["reasoning_effort"],
        "source_sha256": {
            name: sha256_file(path) for name, path in source_paths.items()
        },
        "tool_schema_sha256": (
            canonical_tool_sha(tool)
            if args.shape == "shell"
            else tool_schema_sha256(config)
        ),
        "template": {
            "enable_thinking": "undefined",
            "preserve_thinking": "undefined",
            "add_generation_prompt": False,
            "jinja2_version": jinja2.__version__,
        },
        "counts": {
            "examples": len(examples),
            "failure_tasks": len(failure_ids),
            "control_tasks": len(control_ids),
            "by_task": by_task,
            "by_category": {
                category: sum(
                    1 for example in examples if example["category"] == category
                )
                for category in sorted({e["category"] for e in examples})
            },
        },
        "held_out": {
            "eval_prompt_count": len(eval_prompts),
            "collisions": collisions,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(json.dumps(example, ensure_ascii=False, sort_keys=True) + "\n")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {len(examples)} examples to {output_path.relative_to(ROOT)} "
        f"(shape={args.shape}, {len(failure_ids)} failure tasks, "
        f"{len(control_ids)} control tasks)"
    )
    print(f"wrote manifest to {manifest_path.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
