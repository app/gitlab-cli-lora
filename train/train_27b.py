"""QLoRA training for native-XML glab tool calls on Qwen3.8-27B."""

from __future__ import annotations

import difflib
import hashlib
import importlib.metadata
import json
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from unsloth import FastModel
from unsloth.chat_templates import train_on_responses_only

import torch
from datasets import Dataset
from transformers import AutoTokenizer, TrainerCallback
from trl import SFTConfig, SFTTrainer

ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "glab-eval"
DATA_DIR = ROOT / "train" / "data"
# Mix of dataset directories under train/data, family/shape/lang:
# "tasks/glab/en,tasks/shell/en,url/shell/ru" etc.
# TRAIN_LANGS stays supported as the legacy glab-only task mix ("en,ru").
def _dataset_mix() -> tuple[str, ...]:
    raw = os.environ.get("TRAIN_MIX")
    if raw is not None:
        items = [item.strip() for item in raw.split(",")]
    else:
        legacy = os.environ.get("TRAIN_LANGS", "en,ru")
        items = [f"tasks/glab/{item.strip()}" for item in legacy.split(",")]
    return tuple(item for item in items if item)


DATASET_DIRS = _dataset_mix()
DATA_PATHS = {name: DATA_DIR / name / "sft.jsonl" for name in DATASET_DIRS}
MANIFEST_PATHS = {
    name: DATA_DIR / name / "dataset_manifest.json" for name in DATASET_DIRS
}
OPENCODE_DIR = DATA_DIR / "contracts" / "opencode"
TEMPLATE_PATH = EVAL_ROOT / "docs" / "chat_template.jinja"

sys.path.insert(0, str(EVAL_ROOT))

from common import (  # noqa: E402
    FUNCTION_RE,
    PARAMETER_RE,
    build_tool,
    load_config,
    sha256_bytes,
    sha256_file,
    tool_schema_sha256,
)

MODEL_NAME = os.environ.get(
    "TRAIN_MODEL", "unsloth/Qwen3.8-27B-unsloth-bnb-4bit"
)
MODE = os.environ.get("TRAIN_MODE", "train")
ARTIFACTS_DIR = Path(
    os.environ.get("ARTIFACTS_DIR", "/workspace/artifacts/runs/glab27b-default")
)
MAX_SEQ_LENGTH = int(os.environ.get("TRAIN_MAX_SEQ_LENGTH", "1024"))
MAX_STEPS = int(os.environ.get("TRAIN_STEPS", "100"))
LORA_R = int(os.environ.get("TRAIN_LORA_R", "16"))
LORA_ALPHA = int(os.environ.get("TRAIN_LORA_ALPHA", "16"))
LEARNING_RATE = float(os.environ.get("TRAIN_LR", "2e-4"))
BATCH_SIZE = int(os.environ.get("TRAIN_BATCH_SIZE", "1"))
GRAD_ACCUM = int(os.environ.get("TRAIN_GRAD_ACCUM", "4"))
SEED = int(os.environ.get("TRAIN_SEED", "3407"))
INFERENCE_CHECK = os.environ.get("TRAIN_INFERENCE", "1") != "0"
HF_TOKEN = os.environ.get("HF_TOKEN") or None

progress: dict[str, Any] = {
    "phase": "init",
    "step": 0,
    "max_steps": MAX_STEPS,
    "loss": None,
}
_stop_heartbeat = threading.Event()
_started = time.monotonic()


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{stamp}] {message}", flush=True)


def heartbeat() -> None:
    while not _stop_heartbeat.wait(30):
        elapsed = time.monotonic() - _started
        log(
            "heartbeat phase={phase} step={step}/{max_steps} loss={loss} "
            "elapsed={elapsed:.0f}s".format(**progress, elapsed=elapsed)
        )


def load_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in DATASET_DIRS:
        path = DATA_PATHS[name]
        dataset_rows = 0
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                row["_dataset"] = name
                row["_shape"] = row.get("shape", "glab")
                row["_line"] = line_number
                rows.append(row)
                dataset_rows += 1
        log(
            f"dataset dir={name} rows={dataset_rows} "
            f"path={path.relative_to(ROOT)} shape={rows[-1]['_shape']}"
        )
    log(f"dataset total rows={len(rows)} dirs={','.join(DATASET_DIRS)}")
    return rows


REQUIRED_SOURCES: dict[tuple[str, str], set[str]] = {
    ("tasks", "glab"): {
        "config.yaml",
        "tasks.jsonl",
        "chat_template.jinja",
        "training_handoff.json",
        "paraphrases.jsonl",
        "build_dataset.py",
    },
    ("tasks", "shell"): {
        "tasks.jsonl",
        "chat_template.jinja",
        "training_handoff.json",
        "paraphrases.jsonl",
        "build_dataset.py",
        "shell-tool.json",
        "system-prompt.txt",
    },
    ("url", "glab"): {
        "config.yaml",
        "slots.jsonl",
        "phrasings.json",
        "chat_template.jinja",
        "build_dataset.py",
    },
    ("url", "shell"): {
        "slots.jsonl",
        "phrasings.json",
        "chat_template.jinja",
        "build_dataset.py",
        "shell-tool.json",
        "system-prompt.txt",
        "system-prompt.raw.txt",
        "capture-request.json",
    },
    ("ext", "shell"): {
        "tasks.ext.jsonl",
        "chat_template.jinja",
        "build_dataset.py",
        "shell-tool.json",
        "system-prompt.txt",
        "system-prompt.raw.txt",
        "capture-request.json",
    },
}


def dataset_source_path(name: str, lang: str, handoff_run: str) -> Path:
    if name == "tasks.ext.jsonl":
        return DATA_DIR / "ext" / "spec" / "tasks.ext.jsonl"
    if name.startswith("help-"):
        return EVAL_ROOT / "docs" / name
    if name == "slots.jsonl":
        return DATA_DIR / "url" / "spec" / "slots.jsonl"
    if name == "phrasings.json":
        return DATA_DIR / "url" / "spec" / "phrasings.json"
    if name == "paraphrases.jsonl":
        return DATA_DIR / "tasks" / "spec" / f"paraphrases.{lang}.jsonl"
    if name == "training_handoff.json":
        return EVAL_ROOT / "results" / handoff_run / name
    if name == "chat_template.jinja":
        return TEMPLATE_PATH
    if name == "build_dataset.py":
        return ROOT / "train" / "build_dataset.py"
    if name in ("shell-tool.json", "system-prompt.txt", "system-prompt.raw.txt", "capture-request.json"):
        return OPENCODE_DIR / name
    return EVAL_ROOT / name


def expected_tool_schema_sha(shape: str, config: dict[str, Any]) -> str:
    """Tool schema hash a dataset manifest must carry for a given shape."""
    if shape != "shell":
        return tool_schema_sha256(config)
    tool = json.loads((OPENCODE_DIR / "shell-tool.json").read_text(encoding="utf-8"))
    return sha256_bytes(
        json.dumps(
            tool, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    )


def validate_artifacts(
    rows: list[dict[str, Any]], config: dict[str, Any]
) -> dict[str, Any]:
    index = json.loads((EVAL_ROOT / "results" / "index.json").read_text(encoding="utf-8"))
    handoff_run = index["suites"]["baseline"]["runs"][0]["run_id"]
    datasets: dict[str, Any] = {}
    for name in DATASET_DIRS:
        dataset_manifest = json.loads(MANIFEST_PATHS[name].read_text(encoding="utf-8"))
        lang = dataset_manifest.get("lang")
        if lang not in ("en", "ru"):
            raise RuntimeError(f"{name}: manifest lang={lang!r}")
        shape = dataset_manifest.get("shape", "glab")
        family = dataset_manifest.get("family", "tasks")
        if (family, shape) not in REQUIRED_SOURCES:
            raise RuntimeError(f"{name}: unknown family/shape {family}/{shape}")
        entries = dataset_manifest["source_sha256"]
        missing = REQUIRED_SOURCES[(family, shape)] - set(entries)
        if missing:
            raise RuntimeError(f"{name}: manifest misses sources {sorted(missing)}")
        for source_name, expected in entries.items():
            actual = sha256_file(dataset_source_path(source_name, lang, handoff_run))
            if expected != actual:
                raise RuntimeError(
                    f"{name}: stale dataset source {source_name}: "
                    f"manifest={expected} actual={actual}"
                )
        schema_hash = expected_tool_schema_sha(shape, config)
        if dataset_manifest["tool_schema_sha256"] != schema_hash:
            raise RuntimeError(
                f"{name}: tool schema changed since the dataset was built: "
                f"manifest={dataset_manifest['tool_schema_sha256']} actual={schema_hash}"
            )
        dir_rows = sum(1 for row in rows if row["_dataset"] == name)
        if dir_rows != dataset_manifest["counts"]["examples"]:
            raise RuntimeError(
                f"{name}: dataset row count {dir_rows} != manifest "
                f"{dataset_manifest['counts']['examples']}"
            )
        datasets[name] = {
            "lang": lang,
            "family": family,
            "shape": shape,
            "examples": dir_rows,
            "manifest_sha256": sha256_file(MANIFEST_PATHS[name]),
        }
    log(
        f"artifacts OK dirs={','.join(DATASET_DIRS)} "
        f"template_sha256={sha256_file(TEMPLATE_PATH)[:12]}"
    )
    return datasets


def load_contracts(config: dict[str, Any]) -> dict[str, tuple[dict[str, Any], str | None]]:
    """Per-shape render contract: (tool object, system prompt or None)."""
    shell_tool = json.loads((OPENCODE_DIR / "shell-tool.json").read_text(encoding="utf-8"))
    shell_system = (OPENCODE_DIR / "system-prompt.txt").read_text(encoding="utf-8")
    return {
        "glab": (build_tool(config), None),
        "shell": (shell_tool, shell_system),
    }


def assistant_messages(
    row: dict[str, Any],
    tool: dict[str, Any],
    system_prompt: str | None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if system_prompt is not None:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(
        [
            {"role": "user", "content": row["prompt"]},
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
                            "arguments": {"command": row["expected_command"]},
                        },
                    }
                ],
            },
        ]
    )
    return messages


def render_with_tokenizer(
    tokenizer: Any,
    row: dict[str, Any],
    tool: dict[str, Any],
    system_prompt: str | None,
    reasoning_effort: str,
) -> str:
    return tokenizer.apply_chat_template(
        assistant_messages(row, tool, system_prompt),
        tools=[tool],
        tokenize=False,
        add_generation_prompt=False,
        reasoning_effort=reasoning_effort,
    )


def first_difference(actual: str, expected: str) -> int:
    limit = min(len(actual), len(expected))
    for index in range(limit):
        if actual[index] != expected[index]:
            return index
    return limit


def load_frozen_tokenizer() -> Any:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, token=HF_TOKEN)
    # The prequantized 4-bit repo has no chat_template. The eval endpoint uses
    # the frozen snapshot, so training must use the exact same template.
    tokenizer.chat_template = template
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    log(f"tokenizer loaded model={MODEL_NAME} chat_template set from frozen snapshot")
    return tokenizer


def check_parity(
    tokenizer: Any,
    rows: list[dict[str, Any]],
    contracts: dict[str, tuple[dict[str, Any], str | None]],
    reasoning_effort: str,
) -> None:
    mismatches: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        tool, system_prompt = contracts[row["_shape"]]
        actual = render_with_tokenizer(
            tokenizer, row, tool, system_prompt, reasoning_effort
        )
        expected = row["text"]
        if actual != expected:
            at = first_difference(actual, expected)
            diff = "\n".join(
                list(
                    difflib.unified_diff(
                        expected.splitlines(keepends=True),
                        actual.splitlines(keepends=True),
                        fromfile="stored",
                        tofile="tokenizer",
                        n=2,
                    )
                )[:24]
            )
            mismatches.append(
                {
                    "id": row["id"],
                    "line": row["_line"],
                    "first_difference": at,
                    "stored_length": len(expected),
                    "tokenizer_length": len(actual),
                    "diff": diff,
                }
            )
            if len(mismatches) >= 3:
                break
        if index % 30 == 0:
            log(f"parity progress={index}/{len(rows)}")

    if mismatches:
        raise RuntimeError(
            "chat template parity failed:\n"
            + json.dumps(mismatches, indent=2, ensure_ascii=False)
        )
    log(f"parity OK examples={len(rows)} reasoning_effort={reasoning_effort}")


def check_token_lengths(
    tokenizer: Any, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Fail fast if any row does not fit max_seq_length (right truncation
    would silently cut the assistant target)."""
    lengths = [
        len(tokenizer(row["text"], add_special_tokens=False)["input_ids"])
        for row in rows
    ]
    if not lengths:
        raise RuntimeError("no rows to measure")
    over = sum(1 for value in lengths if value > MAX_SEQ_LENGTH)
    report = {
        "token_length_max": max(lengths),
        "token_length_mean": round(sum(lengths) / len(lengths), 1),
        "token_length_over_max_seq": over,
    }
    log(
        f"token lengths max={report['token_length_max']} "
        f"mean={report['token_length_mean']} over_max_seq={over} "
        f"max_seq_length={MAX_SEQ_LENGTH}"
    )
    if over:
        raise RuntimeError(
            f"{over} rows exceed TRAIN_MAX_SEQ_LENGTH={MAX_SEQ_LENGTH}; "
            "raise the limit before training"
        )
    return report


def versions() -> dict[str, str]:
    result: dict[str, str] = {}
    for name in (
        "torch",
        "transformers",
        "trl",
        "datasets",
        "unsloth",
        "unsloth_zoo",
        "accelerate",
        "peft",
        "bitsandbytes",
    ):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = "missing"
    return result


def adapter_hashes(adapter_dir: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(adapter_dir.iterdir())
        if path.is_file()
    }


def write_manifest(rows: list[dict[str, Any]], extra: dict[str, Any]) -> Path:
    peak = torch.cuda.max_memory_allocated() / 2**30 if torch.cuda.is_available() else 0.0
    manifest = {
        "run_type": "glab27b" if MODE == "train" else "glab27b-check",
        "run_name": ARTIFACTS_DIR.name,
        "mode": MODE,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_name": MODEL_NAME,
        "datasets": {
            name: str(DATA_PATHS[name].relative_to(ROOT)) for name in DATASET_DIRS
        },
        "dataset_examples": len(rows),
        "dataset_manifest_sha256": {
            name: sha256_file(MANIFEST_PATHS[name]) for name in DATASET_DIRS
        },
        "chat_template_sha256": sha256_file(TEMPLATE_PATH),
        "target_format": "qwen3_5_native_xml",
        "max_seq_length": MAX_SEQ_LENGTH,
        "elapsed_seconds": round(time.monotonic() - _started, 1),
        "vram_peak_gib": round(peak, 2),
        "versions": versions(),
    }
    manifest.update(extra)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS_DIR / "manifest.json"
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    log(f"manifest written to {path}")
    return path


class ProgressCallback(TrainerCallback):
    def on_train_begin(self, args, state, control, **kwargs):
        progress["phase"] = "train"
        log(f"train begin max_steps={state.max_steps}")

    def on_step_end(self, args, state, control, **kwargs):
        progress["step"] = state.global_step
        peak = torch.cuda.max_memory_allocated() / 2**30 if torch.cuda.is_available() else 0.0
        log(
            f"train step={state.global_step}/{state.max_steps} "
            f"vram_peak_gib={peak:.2f}"
        )

    def on_log(self, args, state, control, logs=None, **kwargs):
        if not logs:
            return
        progress["loss"] = logs.get("loss")
        details = " ".join(f"{key}={value}" for key, value in logs.items())
        log(f"train metric {details}")

    def on_train_end(self, args, state, control, **kwargs):
        log("train end")


def inference_check(
    model: Any,
    tokenizer: Any,
    contracts: dict[str, tuple[dict[str, Any], str | None]],
    row: dict[str, Any],
    reasoning_effort: str,
) -> dict[str, Any]:
    tool, system_prompt = contracts[row["_shape"]]
    messages: list[dict[str, Any]] = []
    if system_prompt is not None:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": row["prompt"]})
    prompt = tokenizer.apply_chat_template(
        messages,
        tools=[tool],
        tokenize=False,
        add_generation_prompt=True,
        reasoning_effort=reasoning_effort,
    )
    # The 27B tokenizer is a VLM processor: the first positional argument is
    # images, so the text must be passed by keyword to avoid image decoding.
    inputs = tokenizer(text=[prompt], return_tensors="pt").to(model.device)
    FastModel.for_inference(model)
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=160,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
        )
    raw = tokenizer.decode(
        output[0][inputs["input_ids"].shape[1] :], skip_special_tokens=False
    )
    functions = FUNCTION_RE.findall(raw)
    parameters = PARAMETER_RE.findall(raw)
    command = parameters[0][1].strip() if parameters else None
    log("inference raw=" + raw[:500].replace("\n", "\\n"))
    return {
        "prompt": row["prompt"],
        "expected_command": row["expected_command"],
        "model_command": command,
        "match": command == row["expected_command"],
        "functions": functions,
        "raw": raw[:1000],
    }


def run_training(
    rows: list[dict[str, Any]],
    contracts: dict[str, tuple[dict[str, Any], str | None]],
    reasoning_effort: str,
    datasets_report: dict[str, Any],
) -> dict[str, Any]:
    progress["phase"] = "load_model"
    torch.cuda.reset_peak_memory_stats()
    model, tokenizer = FastModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
        load_in_8bit=False,
        full_finetuning=False,
        offload_embedding=True,
        token=HF_TOKEN,
    )
    tokenizer.chat_template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    check_parity(tokenizer, rows[:1], contracts, reasoning_effort)
    log("model loaded")

    progress["phase"] = "lora"
    model = FastModel.get_peft_model(
        model,
        finetune_vision_layers=False,
        finetune_language_layers=True,
        finetune_attention_modules=True,
        finetune_mlp_modules=True,
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=SEED,
        use_rslora=False,
        loftq_config=None,
    )
    log(f"LoRA attached r={LORA_R} alpha={LORA_ALPHA}")

    progress["phase"] = "trainer"
    # The mix spans two shapes whose JSONL rows carry different auxiliary
    # columns (shell rows add `shape`), and `datasets.load_dataset` refuses to
    # merge files whose columns differ. Training only consumes the rendered
    # `text`, so build the container in memory instead of merging files.
    train_dataset = Dataset.from_list([{"text": row["text"]} for row in rows])
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=None,
        args=SFTConfig(
            dataset_text_field="text",
            max_length=MAX_SEQ_LENGTH,
            per_device_train_batch_size=BATCH_SIZE,
            gradient_accumulation_steps=GRAD_ACCUM,
            warmup_steps=min(10, max(1, MAX_STEPS // 10)),
            max_steps=MAX_STEPS,
            learning_rate=LEARNING_RATE,
            logging_steps=1,
            optim="adamw_8bit",
            weight_decay=0.0,
            lr_scheduler_type="linear",
            seed=SEED,
            dataset_num_proc=1,
            save_strategy="no",
            report_to="none",
        ),
        callbacks=[ProgressCallback()],
    )
    trainer = train_on_responses_only(
        trainer,
        instruction_part="<|im_start|>user\n",
        response_part="<|im_start|>assistant\n",
    )
    log("trainer ready")

    progress["phase"] = "train"
    trainer.train()

    progress["phase"] = "save"
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    adapter_dir = ARTIFACTS_DIR / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    log(f"adapter saved to {adapter_dir}")

    preview: dict[str, Any] | None = None
    if INFERENCE_CHECK:
        progress["phase"] = "inference"
        try:
            preview = inference_check(model, tokenizer, contracts, rows[0], reasoning_effort)
        except Exception as exc:
            # The adapter and manifest are the valuable artifacts; a failed
            # generation preview must not turn a completed training run into a
            # failed workflow run.
            log(f"inference check failed, continuing: {exc}")
            preview = {"error": str(exc), "match": False}

    return {
        "train_rows": len(rows),
        "max_steps": MAX_STEPS,
        "lora_r": LORA_R,
        "lora_alpha": LORA_ALPHA,
        "learning_rate": LEARNING_RATE,
        "batch_size": BATCH_SIZE,
        "gradient_accumulation_steps": GRAD_ACCUM,
        "seed": SEED,
        "reasoning_effort": reasoning_effort,
        "adapter_dir": str(adapter_dir),
        "adapter_sha256": adapter_hashes(adapter_dir),
        "dataset_sources": datasets_report,
        "inference_preview": preview,
    }


def main() -> None:
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        if MODE not in {"check", "train"}:
            raise ValueError(f"TRAIN_MODE must be check or train, got {MODE!r}")
        log(
            f"start mode={MODE} model={MODEL_NAME} steps={MAX_STEPS} "
            f"seq={MAX_SEQ_LENGTH} artifacts={ARTIFACTS_DIR}"
        )

        progress["phase"] = "validate"
        rows = load_rows()
        config = load_config()
        datasets_report = validate_artifacts(rows, config)
        reasoning_effort = config["generation"]["reasoning_effort"]
        if reasoning_effort != "low":
            raise RuntimeError(f"expected reasoning_effort=low, got {reasoning_effort!r}")
        contracts = load_contracts(config)

        progress["phase"] = "parity"
        tokenizer = load_frozen_tokenizer()
        check_parity(tokenizer, rows, contracts, reasoning_effort)
        progress["phase"] = "lengths"
        length_report = check_token_lengths(tokenizer, rows)

        if MODE == "check":
            write_manifest(
                rows,
                {
                    "check": "frozen chat template parity",
                    "parity_examples": len(rows),
                    "reasoning_effort": reasoning_effort,
                    "datasets": datasets_report,
                    **length_report,
                },
            )
            return

        extra = run_training(rows, contracts, reasoning_effort, datasets_report)
        extra.update(length_report)
        write_manifest(rows, extra)
    except Exception:
        log("fatal error:\n" + traceback.format_exc())
        raise
    finally:
        progress["phase"] = "done"
        _stop_heartbeat.set()
        log(f"done elapsed={time.monotonic() - _started:.1f}s")


if __name__ == "__main__":
    main()
