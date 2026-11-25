# Handoff: attach the glab LoRA adapter in `llm-server`

This repository produced and validated a QLoRA adapter for Qwen3.8-27B that
teaches the model to emit correct `glab` CLI commands. The adapter was converted
to a llama.cpp GGUF LoRA and handed over to a separate serving repository
(`llm-server`), which owns inference runtimes and model definitions. The
runtime work is complete; this document records the final configuration and
verification results.

No `glab` command is ever executed during training, evaluation or validation;
the CLI is only a source of command syntax.

## Status

- Serving change #1 implemented the profile and closed after all acceptance
  criteria passed.
- Serving change #2 pinned the base GGUF revision in both 27B profiles; the
  optional MTP+LoRA A/B was completed there as well.
- The adapter profile is the running default at 192k. The original
  `qwen3.8-27b-gguf` profile is unchanged and remains the rollback.

## Artifacts

The source adapter stays on the GPU host:

```text
/srv/containers/runner/training/qwen38-27b-lora/runs/glab27b-train-20261125T095636Z/adapter
```

The conversion workflow `convert-lora-gguf.yaml` in this repository converts it
to a llama.cpp GGUF adapter and writes the output next to the base GGUF files:

```text
/srv/containers/runner/unsloth/models/Qwen3.8-27B-GGUF/glab27b-q8_0.gguf            # stable symlink
/srv/containers/runner/unsloth/models/Qwen3.8-27B-GGUF/glab27b-q8_0-<UTC stamp>.gguf
/srv/containers/runner/unsloth/models/Qwen3.8-27B-GGUF/glab27b-chat-template.jinja
```

The exact output name, SHA256, size, converter path and library versions are in
`manifest.json` on the report branch `ci/lora-gguf-report`. Do not copy weights
into git.

The live target since 2026-11-25 is `glab27b-q8_0-20261125T122108Z.gguf`
(182,652,096 bytes, SHA256
`f579afe8b72c16adf464bdc7272afa9d7cac1b0eb82ccf8f32e344645137e76e`), built from
the attempt-1.5 adapter (`glab27b-train-20261125T095636Z`, 888 rows). The export
contains both attention and `ssm_*` (linear-attention) LoRA tensors. The frozen
chat template at `glab27b-chat-template.jinja` has SHA256
`af16f654968d47d09a6c604e00370b12dbc21f76456f59c9e98b82e84d9f6375`. The
converter needed `quantization_config` removed from a temporary copy of the
training base config because the PEFT adapter itself is unquantised; the
workflow does this automatically and records it in the manifest.

Live verification on the deployed stack (llama.cpp, `qwen3.8-27b-glab27b`,
temp 1.0): 29/30 samples of "прочитай командой glab
https://gitlab.com/all-projectplus-stuff/issue/-/work_items/117" called `shell`
with `glab issue view <url>`; one sample chose `glob`. Held-out project and
held-out phrasing: 10/10 each. The same 50-prompt probe under vLLM gave 30/30.

Historical-corpus check (the four unique prompts from
`glab-errors-sessions/errors.jsonl`, 10 samples each): 38/40 correct
`issue view` calls. The two misses were one empty answer and one `webfetch` on
`прочитай <url>` without the word "glab" — the only residual nudge toward the
browser tool; artifact at `lora-eval/probes/prod-corpus-20261125T130012Z/`.

Commands to inspect or regenerate:

```sh
# Environment probe (read-only)
curl -fsS -X POST \
  -H "Authorization: token $FORGEJO_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FORGEJO_URL/api/v1/repos/ai/qwen38-27b-lora/actions/workflows/convert-lora-gguf.yaml/dispatches" \
  -d '{"ref":"main","inputs":{"action":"check"},"return_run_info":true}'

# Conversion (CPU only; does not need the GPU lock)
curl -fsS -X POST \
  -H "Authorization: token $FORGEJO_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FORGEJO_URL/api/v1/repos/ai/qwen38-27b-lora/actions/workflows/convert-lora-gguf.yaml/dispatches" \
  -d '{"ref":"main","inputs":{"action":"convert","outtype":"q8_0"},"return_run_info":true}'
```

## Implemented profile

`models/qwen3.8-27b-gguf-glab27b.env` in `ai/llm-server`:

```sh
ENGINE=unsloth
DESCRIPTION="Qwen3.8 27B GGUF + glab LoRA (UD-IQ4_XS) - text-only, 192k default"
LLAMA_REPO=unsloth/Qwen3.8-27B-GGUF
QUANT=UD-IQ4_XS
MODEL_FILE=Qwen3.8-27B-UD-IQ4_XS.gguf
MTP_FILE=MTP/mtp-Qwen3.8-27B-Q4_0.gguf
SERVED_NAME=qwen3.8-27b-glab27b
IMAGE=docker.io/unsloth/unsloth:core-nightly-2026.11.08
PORT=8000
CTX=196608
THREADS=16
KV_TYPE=q8_0
EXTRA_ARGS="--temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.0 --lora /workspace/models/Qwen3.8-27B-GGUF/glab27b-q8_0.gguf --chat-template-file /workspace/models/Qwen3.8-27B-GGUF/glab27b-chat-template.jinja"
```

Configuration notes:

- `scripts/unsloth.sh` appends `EXTRA_ARGS` verbatim to `llama-server`. Its
  `--jinja` flag stays **before** `--chat-template-file`; the frozen template is
  required because training targets were rendered with
  `glab-eval/docs/chat_template.jinja`.
- `llama-server` applies a loaded adapter with scale 1 by default. `GET
/lora-adapters` reports one adapter with scale `1.0`;
  `--lora-init-without-apply` is not used.
- The base file is UD3.1, revision
  `4af51b3542f775b0a8e4b310bfb3f17e01c306c9`, 13.37 GiB. The `QUANT` label in
  the env file is still `UD-IQ4_XS`; the exact revision is pinned with
  `HF_REVISION` in both 27B profiles (commit `4d8ff4e`). `pull` reports the
  resolved revision matching the pin and no download.
- MTP is enabled. The first validation ran with MTP off at 64k, then the profile
  moved to the native 192k window with the draft model enabled.

## Verification in `llm-server`

All five acceptance criteria from issue #1 passed: `list`/`deploy`/`start`, both
model and adapter endpoints, parsed tool calls, rollback to the plain profile,
and no executed `glab` command. Prompt results:

- "List open issues assigned to me in my current project." →
  `glab issue list --assignee=@me`
- "Show the last pipeline for the current merge request." → `glab ci status`

Context probes at ~190k tokens passed at depth 0.5 and 0.9, and the tool probe
returned a parsed tool call at 190 282 tokens.

MTP A/B at 192k (2026-11-22):

| Metric                       | MTP off       | MTP on         |
| ---------------------------- | ------------- | -------------- |
| VRAM used of 24 455 MiB      | 21 428–21 434 | 23 818–23 886  |
| Free                         | ~3.0 GiB      | ~0.6 GiB       |
| Tool calls at 192k           | ok            | ok             |
| Needle 190k, depth 0.5 / 0.9 | ok / ok       | ok / ok        |
| Tool probe 190k              | ok            | ok             |
| Draft acceptance             | —             | 1.00 and 0.955 |
| Prefill 190k                 | 161–166 s     | 171–175 s      |

The adapter does not break speculative decoding. MTP costs about 2.4 GiB and
makes prefill 6–9% slower, so the profile has no reserve for a larger window.
Decode throughput with and without the draft was not reported in the A/B.

## OpenCode entry still needed

This repository does not change global OpenCode config. Add the served id to
the `local-unsloth` provider:

```jsonc
"local-unsloth": {
  "settings": { "baseURL": "http://127.0.0.1:8000/v1" },
  "models": {
    "qwen3.8-27b-glab27b": {
      "name": "Qwen3.8 27B GGUF + glab LoRA 192k",
      "limit": { "context": 196608, "output": 32768 },
      "capabilities": {
        "tools": true,
        "reasoning": { "supported": true },
        "input": ["text"],
        "output": ["text"]
      }
    }
  }
}
```

## Remaining risks

- The adapter is generation-bound: a new base model generation requires a new
  adapter, not just a new chat template. The UD3.0 → UD3.1 revision change was
  harmless, but future generations must be re-validated.
- With MTP enabled there is only ~0.6 GiB of VRAM headroom at 192k. The pinned
  revision prevents silent weight swaps, but any deliberate base bump must be
  followed by `pull`, `scripts/context_probe.py` and a VRAM re-measurement, as
  documented in `llm-server/docs/models.md`.

## Reference results

The same adapter on the vLLM NVFP4 base improved mean pass rate from `0.4201`
to `0.8509` over three independent runs of the frozen 38-task harness; details
are in [`../lora-eval/results/compare.md`](../lora-eval/results/compare.md).
Those numbers are a quality reference, not an expectation that the GGUF runtime
will score identically: different quantisation, KV cache and tool-call parser
can change the result. The GGUF path was validated with smoke probes, not with
the full harness.
