"""Smoke QLoRA run converted from the Unsloth Qwen3 4B Tool Calling notebook."""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
import threading
import time
from datetime import datetime, timezone

from unsloth import FastLanguageModel
from unsloth.chat_templates import train_on_responses_only

import torch
from datasets import load_dataset
from transformers import TrainerCallback
from trl import SFTConfig, SFTTrainer

MODEL_NAME = os.environ.get(
    "SMOKE_MODEL", "unsloth/Qwen3-4B-Instruct-2507-unsloth-bnb-4bit"
)
DATASET_NAME = os.environ.get(
    "SMOKE_DATASET", "NousResearch/hermes-function-calling-v1"
)
DATASET_CONFIG = os.environ.get("SMOKE_DATASET_CONFIG", "func_calling")
ARTIFACTS_DIR = os.environ.get("ARTIFACTS_DIR", "/workspace/artifacts/runs/smoke4b")
MAX_SEQ_LENGTH = int(os.environ.get("SMOKE_MAX_SEQ_LENGTH", "4096"))
MAX_STEPS = int(os.environ.get("SMOKE_STEPS", "10"))
RAW_LIMIT = int(os.environ.get("SMOKE_RAW_LIMIT", "256"))
DATASET_SIZE = int(os.environ.get("SMOKE_DATASET_SIZE", "64"))
SEED = int(os.environ.get("SMOKE_SEED", "3407"))
INFERENCE_CHECK = os.environ.get("SMOKE_INFERENCE", "1") != "0"
HF_TOKEN = os.environ.get("HF_TOKEN") or None

TOOL_CALL_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
TOOL_RESPONSE_RE = re.compile(r"<tool_response>\s*(.*?)\s*</tool_response>", re.DOTALL)

progress = {"phase": "init", "step": 0, "max_steps": MAX_STEPS, "loss": None}
_stop_heartbeat = threading.Event()


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{stamp}] {message}", flush=True)


def heartbeat() -> None:
    started = time.monotonic()
    while not _stop_heartbeat.wait(30):
        elapsed = time.monotonic() - started
        log(
            "heartbeat phase={phase} step={step}/{max_steps} loss={loss} "
            "elapsed={elapsed:.0f}s".format(**progress, elapsed=elapsed)
        )


def to_messages(example: dict) -> tuple[list[dict], list[dict]]:
    """Convert the notebook's text-format tool calls into OpenAI-style messages."""
    messages: list[dict] = []
    for turn in example["conversations"]:
        role, text = turn["from"], turn["value"]
        if role == "system":
            continue
        if role == "human":
            messages.append({"role": "user", "content": text})
        elif role == "gpt":
            calls = [json.loads(call) for call in TOOL_CALL_RE.findall(text)]
            message = {
                "role": "assistant",
                "content": TOOL_CALL_RE.sub("", text).strip(),
            }
            if calls:
                message["tool_calls"] = [
                    {
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": call["arguments"],
                        },
                    }
                    for call in calls
                ]
            messages.append(message)
        elif role == "tool":
            for response in TOOL_RESPONSE_RE.findall(text):
                messages.append({"role": "tool", "content": response})
    return messages, json.loads(example["tools"])


def formatting_prompts_func(examples: dict, tokenizer) -> dict:
    texts: list[str] = []
    for conversations, tools in zip(examples["conversations"], examples["tools"]):
        try:
            messages, parsed_tools = to_messages(
                {"conversations": conversations, "tools": tools}
            )
            texts.append(
                tokenizer.apply_chat_template(
                    messages, tools=parsed_tools, tokenize=False
                )
            )
        except Exception:
            texts.append("")
    return {"text": texts}


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


def inference_check(model, tokenizer) -> str:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "glab_issue_list",
                "description": "List issues in the current project",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
    ]
    messages = [{"role": "user", "content": "Show open issues in my project."}]
    prompt = tokenizer.apply_chat_template(
        messages, tools=tools, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer([prompt], return_tensors="pt").to(model.device)
    FastLanguageModel.for_inference(model)
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=128,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
        )
    text = tokenizer.decode(
        output[0][inputs.input_ids.shape[1] :], skip_special_tokens=False
    )
    log("inference raw=" + text[:500].replace("\n", "\\n"))
    return text[:500]


def main() -> None:
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    started = time.monotonic()
    log(
        f"start model={MODEL_NAME} dataset={DATASET_NAME} "
        f"steps={MAX_STEPS} seq={MAX_SEQ_LENGTH}"
    )

    progress["phase"] = "load_model"
    torch.cuda.reset_peak_memory_stats()
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
        load_in_8bit=False,
        full_finetuning=False,
        token=HF_TOKEN,
    )
    log("model loaded")

    progress["phase"] = "load_dataset"
    full = load_dataset(DATASET_NAME, DATASET_CONFIG, split="train", token=HF_TOKEN)
    raw = full.select(range(min(RAW_LIMIT, len(full))))
    log(f"raw dataset rows={len(raw)}")

    progress["phase"] = "format"
    formatted = raw.map(
        lambda batch: formatting_prompts_func(batch, tokenizer), batched=True
    )
    formatted = formatted.filter(lambda row: len(row["text"]) != 0)
    formatted = formatted.select(range(min(DATASET_SIZE, len(formatted))))
    log(f"formatted dataset rows={len(formatted)}")
    log(f"first sample={formatted[0]['text'][:300].replace(chr(10), '\\n')}")

    progress["phase"] = "lora"
    model = FastLanguageModel.get_peft_model(
        model,
        r=32,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=32,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=SEED,
        use_rslora=False,
        loftq_config=None,
    )
    log("LoRA attached")

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=formatted,
        eval_dataset=None,
        args=SFTConfig(
            dataset_text_field="text",
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            warmup_steps=min(5, MAX_STEPS // 2),
            max_steps=MAX_STEPS,
            learning_rate=2e-4,
            logging_steps=1,
            optim="adamw_8bit",
            weight_decay=0.001,
            lr_scheduler_type="linear",
            seed=SEED,
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

    trainer.train()

    progress["phase"] = "save"
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    adapter_dir = os.path.join(ARTIFACTS_DIR, "adapter")
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)
    log(f"adapter saved to {adapter_dir}")

    inference_preview = ""
    if INFERENCE_CHECK:
        progress["phase"] = "inference"
        inference_preview = inference_check(model, tokenizer)

    elapsed = time.monotonic() - started
    peak = torch.cuda.max_memory_allocated() / 2**30 if torch.cuda.is_available() else 0.0
    manifest = {
        "run_type": "smoke4b",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_name": MODEL_NAME,
        "dataset_name": DATASET_NAME,
        "dataset_config": DATASET_CONFIG,
        "raw_rows": len(raw),
        "train_rows": len(formatted),
        "max_steps": MAX_STEPS,
        "max_seq_length": MAX_SEQ_LENGTH,
        "seed": SEED,
        "elapsed_seconds": round(elapsed, 1),
        "vram_peak_gib": round(peak, 2),
        "adapter_dir": adapter_dir,
        "inference_preview": inference_preview,
        "versions": {
            name: importlib.metadata.version(name)
            for name in (
                "torch",
                "transformers",
                "trl",
                "datasets",
                "unsloth",
            )
        },
    }
    manifest_path = os.path.join(ARTIFACTS_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")

    progress["phase"] = "done"
    _stop_heartbeat.set()
    log(f"done elapsed={elapsed:.1f}s manifest={manifest_path}")


if __name__ == "__main__":
    main()
