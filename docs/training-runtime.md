# Training runtime

This document is the **Forgejo Actions** path: every command here dispatches a
workflow in `$FORGEJO_URL/api/v1/repos/ai/qwen38-27b-lora/...`, where
`ai/qwen38-27b-lora` is the internal name of this same repository. Without
Forgejo — a GPU on your own host, you inside an agent container — use
[`run-without-ci.md`](run-without-ci.md), which runs the same containers
directly.

This project trains QLoRA adapters on a shared GPU host (RTX 5090 D v2,
24 GiB); the evaluation endpoint defaults to `http://127.0.0.1:8000/v1` and can
be overridden with `GLAB_EVAL_ENDPOINT`. Runtime lifecycle is owned by a
separate serving repository (`llm-server`); training jobs live in this
repository.

## One GPU, one job

- Both the vLLM baseline and training use the whole GPU. They cannot run in
  parallel.
- `ai/llm-server` uses `/srv/containers/runner/gpu.lock`; the training workflow
  takes the same lock for the duration of the `podman run`.
- Stop vLLM before training and start it again afterwards. `stop` removes the
  Quadlet `[Install]` section, so the model does not come back automatically.

```sh
# Stop (before training)
curl -fsS -X POST \
  -H "Authorization: token $FORGEJO_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FORGEJO_URL/api/v1/repos/ai/llm-server/actions/workflows/vllm.yaml/dispatches" \
  -d '{"ref":"main","inputs":{"action":"stop","model":"qwen3.8-27b-nvfp4","tail":"200","report":"false"},"return_run_info":true}'

# Start (after training)
curl -fsS -X POST \
  -H "Authorization: token $FORGEJO_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FORGEJO_URL/api/v1/repos/ai/llm-server/actions/workflows/vllm.yaml/dispatches" \
  -d '{"ref":"main","inputs":{"action":"start","model":"qwen3.8-27b-nvfp4","tail":"200","report":"false"},"return_run_info":true}'
```

Verify recovery with `curl -fsS http://127.0.0.1:8000/v1/models`; the served
id must be `qwen3.8-27b-nvfp4` with root `nvidia/Qwen3.8-27B-NVFP4`.

## Dispatching the smoke workflow

The installed `tea` (0.9.2) has no Actions commands. Use the Forgejo REST API:

```sh
curl -fsS -X POST \
  -H "Authorization: token $FORGEJO_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FORGEJO_URL/api/v1/repos/ai/qwen38-27b-lora/actions/workflows/train-smoke-4b.yaml/dispatches" \
  -d '{"ref":"main","inputs":{"action":"train","max_steps":"10","raw_limit":"256","dataset_size":"64"},"return_run_info":true}'
```

Monitor with:

```sh
curl -fsS -H "Authorization: token $FORGEJO_TOKEN" \
  "$FORGEJO_URL/api/v1/repos/ai/qwen38-27b-lora/actions/runs?limit=5"
```

A run report branch `ci/training-smoke-4b-report` receives `ci-action.log` and
`manifest.json` after every run.

## Dispatching the 27B training workflow

The Iteration 2 workflow is `train-glab-27b.yaml`. It has three actions:

- `check`: install the pinned stack, load only the tokenizer, and verify that the
  real `tokenizer.apply_chat_template` reproduces every stored text byte for
  byte. No weights are loaded and no GPU memory is allocated.
- `train`: run the parity check, load the 4-bit 27B model, attach LoRA, train on
  `train/data/tasks/glab/{en,ru}/sft.jsonl`, save only the adapter, and run one
  generation check.
- `status`: print GPU/disk state and list existing 27B run manifests.

```sh
# First, stop vLLM using the commands above and wait for the run to finish.
curl -fsS -X POST \
  -H "Authorization: token $FORGEJO_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FORGEJO_URL/api/v1/repos/ai/qwen38-27b-lora/actions/workflows/train-glab-27b.yaml/dispatches" \
  -d '{"ref":"main","inputs":{"action":"check"},"return_run_info":true}'

# After the parity check passes. max_steps=200 keeps roughly the same number
# of epochs (about 2) as the 100-step run had on the 180-row English dataset.
curl -fsS -X POST \
  -H "Authorization: token $FORGEJO_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FORGEJO_URL/api/v1/repos/ai/qwen38-27b-lora/actions/workflows/train-glab-27b.yaml/dispatches" \
  -d '{"ref":"main","inputs":{"action":"train","max_steps":"200","lora_r":"16","max_seq_length":"1024","learning_rate":"2e-4","inference":"1"},"return_run_info":true}'

# Finally, start vLLM again and verify /v1/models.
```

The 27B job writes `ci-action.log` and `manifest.json` to the report branch
`ci/training-glab-27b-report`. The adapter itself stays under
`/srv/containers/runner/training/qwen38-27b-lora/runs/glab27b-train-<timestamp>/adapter`.

`train/train_27b.py` imports `unsloth` before `trl` and `transformers`; this is
required for Unsloth's backwards-compatible SFTTrainer patch, which accepts the
`tokenizer=` argument used by both training scripts. The 27B tokenizer is a VLM
processor, so the generation preview passes text with `tokenizer(text=[prompt])`
rather than as a positional argument, which would be interpreted as images.

Python dependencies are pinned in `train/run_train_27b.sh`:
`torch==2.14.1`, `transformers==5.17.0`, `datasets==4.3.0`, `trl==0.22.2`,
`unsloth==2026.11.9`, and `unsloth_zoo==2026.11.8`. With `trl==0.22.2`,
sequence length is passed to `SFTConfig` as `max_length`; `max_seq_length`
belongs to `FastModel.from_pretrained`. The workflow sets
`HF_XET_HIGH_PERFORMANCE=1` instead of using the deprecated
`HF_HUB_ENABLE_HF_TRANSFER`. The model repo has no `chat_template`, so the
script installs the frozen snapshot from `glab-eval/docs/chat_template.jinja`
onto the tokenizer before rendering or training. No `dtype` is forced:
Unsloth keeps Qwen3.5 GDN layers in float32 to avoid NaN gradients.

## What the smoke job does

1. Checkout, verify scripts, check GPU state.
2. Acquire the GPU lock and start a 30-second workflow heartbeat.
3. Run `train/run_smoke_4b.sh` in
   `docker.io/pytorch/pytorch:2.15.0-cuda13.2-cudnn9-runtime` with
   `--device nvidia.com/gpu=all`.
4. Install the notebook's pinned Python dependencies, then run
   `train/smoke_4b.py`.
5. Load `unsloth/Qwen3-4B-Instruct-2507-unsloth-bnb-4bit` with
   `load_in_4bit=True`, LoRA `r=32`, `max_seq_length=4096`, and a small
   `hermes-function-calling-v1` subset.
6. Train 5-10 steps, save only the adapter, run one generation check, and write
   a manifest.

## Training dataset for the 27B adapter

The SFT data is generated per language, not hand-edited, so it stays tied to the
frozen evaluation artifacts:

```sh
cd /path/to/qwen38-27b-lora
uv run --project train python train/build_dataset.py --lang en
uv run --project train python train/build_dataset.py --lang ru
uv run --project train python train/validate_dataset.py --lang all
```

- Layout is family -> shape -> language: `train/data/tasks/glab/<lang>/` and
  `train/data/tasks/shell/<lang>/`, each with `sft.jsonl` and
  `dataset_manifest.json`; the paraphrase specs live in
  `train/data/tasks/spec/`.
  Russian example ids are prefixed with `ru-` so ids stay unique across the
  concatenated 360-row mix; English ids stay bare for byte-identical rebuilds.
- `train/data/tasks/spec/paraphrases.<lang>.jsonl` holds natural alternative phrasings
  keyed by task id. Failure tasks get six per language, control tasks three.
  Russian prompts are written natively, not translated literally.
- `train/build_dataset.py --lang <en|ru>` renders each example with the frozen
  `glab-eval/docs/chat_template.jinja`, the tool schema from
  `glab-eval/config.yaml`, and `reasoning_effort=low`. It rejects prompts that
  collide with either eval set.
- `train/validate_dataset.py --lang all` re-renders every row and checks the
  native XML target, the exact `expected_command`, forbidden patterns,
  read-only commands, source hashes, the held-out prompt rule, and
  cross-language duplicates.
- The chat template ends a generation prompt with `<think>\n`. The target
  therefore starts with an empty `</think>` before the tool call; training the
  model to emit `<tool_call>` immediately would place it inside the think block.

The datasets currently have 180 examples each (22 failure tasks x 6, 16 control
tasks x 3). `train_27b.py` loads `TRAIN_MIX` (comma-separated dataset dirs under
`train/data`, default `en,ru`; `TRAIN_LANGS` still works as the legacy alias),
validates each manifest, and trains on the concatenation: 360 examples at a
50/50 mix.

### Shell-shape datasets (attempt 1)

The production OpenCode contract is one tool, `shell`, behind the long frozen
OpenCode system prompt — not the synthetic `run_glab_command`. Attempt 1
therefore trains on a 720-row mix of both shapes so the adapter keeps the
command knowledge and re-anchors it on the real serving prompt. The exact
prompt/tool bytes live in `train/data/contracts/opencode/` (see its README for capture
provenance, drift notes and the refresh procedure).

```sh
uv run --project train python train/build_dataset.py --shape shell --lang en
uv run --project train python train/build_dataset.py --shape shell --lang ru
uv run --project train python train/validate_dataset.py --lang all   # covers all 4 dirs
```

- Shell rows reuse the same paraphrases and `expected_command` values as the
  glab rows; only the rendered prefix differs (frozen system prompt + `shell`
  tool schema). Ids are `shell-`/`shell-ru-` prefixed to stay unique.
- `train_27b.py` renders shell rows with the frozen system prompt, and
  `check_token_lengths` fails fast if any row exceeds `TRAIN_MAX_SEQ_LENGTH`.
  The frozen prompt is roughly 6k tokens, so shell-shape training needs
  `max_seq_length=8192` (the frozen glab-only runs used 1024).
- The workflow takes the mix as the `dataset_dirs` input, e.g.
  `{"action":"train","dataset_dirs":"tasks/glab/en,tasks/glab/ru,tasks/shell/en,tasks/shell/ru","max_seq_length":"8192",...}`.

### URL-entity datasets (attempt 1.5)

`train/data/url/spec/slots.jsonl` is the slot spec (group, project, iid, URL
form, split); `train/data/url/spec/phrasings.json` is the phrasing table. The
builder crosses them and writes `train/data/url/<shape>/<lang>/` with
`sft.jsonl` (train rows) and `heldout.<lang>.jsonl` (never trained).

```sh
uv run --project train python train/build_dataset.py --family url --shape glab --lang en
uv run --project train python train/build_dataset.py --family url --shape shell --lang ru
uv run --project train python train/validate_dataset.py --family url
```

- Project names deliberately collide with the entity vocabulary (`issue`,
  `work-items`), so the learned rule is structural: any GitLab issue/work-item
  URL maps to `glab issue view <url>`, whatever the path segments say.
- REST phrasing maps to `glab api "projects/<group>%2F<project>/issues/N"`.
  The `work_items` API endpoint is rejected during validation: GitLab returns
  404 for it, and `glab work-items` has no `view` subcommand at 1.100.0.
- Held out: the `acme/tasks` project and the `holdout-read` phrasing per
  language. The validator fails if a held-out prompt leaks into training, and
  the manifests record the held-out ids.
- The frozen 38-task suites are untouched; this family adds 66 rows per
  language and shape (264 in total), mixed with the 720 task rows. Two
  phrasings deliberately omit the word "glab": the live corpus showed that
  phrasing as the only residual nudge toward the browser tool.

Full mix for a retrain:

```text
dataset_dirs=tasks/glab/en,tasks/glab/ru,tasks/shell/en,tasks/shell/ru,url/glab/en,url/glab/ru,url/shell/en,url/shell/ru,ext/shell/en,ext/shell/ru
```

### Ext family (attempt 2, shell only)

`train/data/ext/spec/tasks.ext.jsonl` holds the lean command surface for
attempt 2: `mr diff/approvers/issues`, `ci list/get/trace`, `release
list/view`, `label list`, `repo view`, `issue board view`, plus REST patterns
for issue notes, repository tags, pipelines and paginated issue lists. Each
task carries three EN and three RU prompt phrasings and one canonical command.

- Shell-shape only: the `glab` benchmark contract stays frozen for the 38
  tasks, so new families are not trained in that shape.
- Three tasks are held out (`ci trace`, `release view`, repository tags) and
  never trained; the validator rejects leakage.
- Every task points at a frozen `glab <cmd> --help` snapshot in
  `glab-eval/docs/`, recorded with its SHA256 in `sources.json`.
- GraphQL targets, the `work_items` API endpoint and mutating commands are
  rejected by the validator.

## LoRA adapter evaluation

`glab-eval` stays frozen as the stage-zero diagnostic baseline. The trained
adapter is evaluated by `lora-eval`, which reuses the same harness with an
endpoint override (`GLAB_EVAL_CONFIG=lora-eval/config.yaml`). See
[`lora-eval/README.md`](../lora-eval/README.md) for the config differences.

```sh
# Verify that vLLM accepts LoRA on the frozen NVFP4 base model.
curl -fsS -X POST \
  -H "Authorization: token $FORGEJO_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FORGEJO_URL/api/v1/repos/ai/qwen38-27b-lora/actions/workflows/eval-lora.yaml/dispatches" \
  -d '{"ref":"main","inputs":{"action":"check"},"return_run_info":true}'

# Three independent runs, scoring, and comparison against the baseline.
curl -fsS -X POST \
  -H "Authorization: token $FORGEJO_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FORGEJO_URL/api/v1/repos/ai/qwen38-27b-lora/actions/workflows/eval-lora.yaml/dispatches" \
  -d '{"ref":"main","inputs":{"action":"eval"},"return_run_info":true}'

# The same for the Russian suite: results land in lora-eval/results-ru/.
curl -fsS -X POST \
  -H "Authorization: token $FORGEJO_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FORGEJO_URL/api/v1/repos/ai/qwen38-27b-lora/actions/workflows/eval-lora.yaml/dispatches" \
  -d '{"ref":"main","inputs":{"action":"eval","lang":"ru"},"return_run_info":true}'
```

The job holds the GPU lock, starts vLLM with `--enable-lora`, waits for
`/health`, checks `/v1/models`, runs the harness three times, scores each run,
and writes `compare.json`/`compare.md`. It always stops vLLM on exit. English
results are committed to `main` under `lora-eval/results/`, Russian results
under `lora-eval/results-ru/`; the full CI log lives on `ci/lora-eval-report`.

### Shell-shape evaluation mode

`run_eval.py --mode shell` scores the adapter under the frozen OpenCode
serving contract: messages are `[frozen system prompt, task prompt]` with
`tools=[shell tool]` from `train/data/contracts/opencode/` (paths configurable via the
`shell_mode` section of `lora-eval/config.yaml`). The scored contract includes
the tool name: a call to any other tool is recorded as `wrong_tool` even if the
command string matches. The api/raw payload construction is untouched, so the
frozen suites stay comparable.

```sh
cd glab-eval
GLAB_EVAL_CONFIG=../lora-eval/config.yaml uv run python run_eval.py --suite shell27b --mode shell
GLAB_EVAL_CONFIG=../lora-eval/config.yaml GLAB_EVAL_TASKS=tasks.ru.jsonl \
  uv run python run_eval.py --suite shell27b-ru --mode shell
```

`probe_opencode_payload.py` is the manual multi-tool check: it replays the full
frozen capture (all 14 tools + production system prompt) against the served
endpoint and records which tool the model picks. It is a review artifact, not a
scored suite. The prompt set lives in `glab-eval/probe-prompts.jsonl` (Russian,
realistic OpenCode-style reads), and `eval-lora.yaml` exposes it as the `probe`
action: the job starts the same vLLM + adapter container, runs the probe, and
publishes `probe.json` to `lora-eval/probes/<timestamp>/` on main (and to the CI
report branch with the full log).

The `eval-lora.yaml` workflow takes the same mode as an input; shell results go
to `lora-eval/results-shell{,-ru}/` and are scored but not compared (there is
no frozen baseline for a different contract):

```sh
curl -fsS -X POST \
  -H "Authorization: token $FORGEJO_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FORGEJO_URL/api/v1/repos/ai/qwen38-27b-lora/actions/workflows/eval-lora.yaml/dispatches" \
  -d '{"ref":"main","inputs":{"action":"eval","lang":"en","mode":"shell","adapter_run":"<run>"},"return_run_info":true}'
```

### Russian evaluation

`glab-eval/tasks.ru.jsonl` mirrors the 38 English tasks with Russian prompts.
Expected commands, required flags, forbidden patterns, and source excerpts are
identical; only the prompt differs. `validate_tasks.py` enforces this parity.

```sh
cd glab-eval
GLAB_EVAL_LANG=ru uv run ./run_baseline.sh --rep r1
```

Run three reps, then aggregate and keep the Russian baseline next to the
English one without overwriting it:

```sh
cp results/aggregate.json /tmp/aggregate-en.json
uv run python score.py --aggregate results/baseline-ru-*
cp results/aggregate.json results/aggregate-ru.json
cp /tmp/aggregate-en.json results/aggregate.json
```

The adapter's Russian suite reuses the same workflow with `lang=ru` and compares
against `glab-eval/results/aggregate-ru.json`.

`canonical_hash` covers the harness sources as well as the tasks and docs, so
the shell-mode change gives every new run a new hash (the first one was
`044ff59a`) while the frozen baseline keeps `9ab9b978`. `compare.py` diffs
per-task pass rates and ignores the hash, so the frozen baseline remains the
comparison point; only the aggregate `group_key` label moves.

## GGUF adapter conversion

The same adapter can be converted to a llama.cpp GGUF LoRA so `llm-server` can
attach it to `qwen3.8-27b-gguf`, the 192k model used for normal work. Conversion
is CPU-only and does not need the GPU lock. The workflow
`convert-lora-gguf.yaml` has three actions:

- `check`: verify adapter files and hashes, locate the base config in the HF
  cache, and probe the Unsloth image for `convert_lora_to_gguf.py`, Python
  dependencies and `llama-server --lora`. Read-only.
- `convert`: run the converter with `--outtype q8_0`, place the result next to
  the base GGUF files, copy the frozen chat template, and write a manifest.
- `status`: list produced GGUF adapters and available training runs.

```sh
curl -fsS -X POST \
  -H "Authorization: token $FORGEJO_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FORGEJO_URL/api/v1/repos/ai/qwen38-27b-lora/actions/workflows/convert-lora-gguf.yaml/dispatches" \
  -d '{"ref":"main","inputs":{"action":"check"},"return_run_info":true}'

curl -fsS -X POST \
  -H "Authorization: token $FORGEJO_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FORGEJO_URL/api/v1/repos/ai/qwen38-27b-lora/actions/workflows/convert-lora-gguf.yaml/dispatches" \
  -d '{"ref":"main","inputs":{"action":"convert","outtype":"q8_0"},"return_run_info":true}'
```

Output, symlink and manifest locations are described in
[the `llm-server` handoff](llm-server-lora-handoff.md). The full CI log and
`manifest.json` are published to `ci/lora-gguf-report`; adapter weights stay on
the host. Changing the inference runtime itself belongs to `llm-server`, which
owns model profiles and lifecycle.

## Observability and timeouts

- The smoke workflow job times out after 60 minutes; its `podman run` is capped
  at 45 minutes. The 27B workflow uses 330 and 300 minutes respectively: the
  shell-mix regime (`max_seq_length` 8192, ~3k tokens per row) costs several
  times the compute of the original 1024-token runs, and a cold first run also
  downloads about 22 GB of weights.
- Both workflows print a timestamped heartbeat every 30 seconds while the
  container runs.
- Both Python scripts print timestamped phase markers and a second heartbeat
  every 30 seconds with phase, step, loss, and elapsed time.
- `SFTConfig(logging_steps=1)` plus a `TrainerCallback` logs every step with
  peak VRAM; all Python output is unbuffered and mirrored to `ci-action.log`.
- Expected smoke duration: 10-25 minutes end to end. Expected 27B `check`
  duration: about 10-15 minutes on a cold pip cache. Expected 27B `train`
  duration: 30-90 minutes on the glab-only mix at 1024 tokens; the shell mix
  at 8192 is several times heavier, so budget 2-4 hours and rely on the
  raised timeouts above.

## Artifacts

All weights and caches stay on the GPU host; git stores only logs and metadata.

```text
/srv/containers/runner/training/qwen38-27b-lora/
├── hf/                         # Hugging Face cache for training
├── pip-cache/                  # reusable pip wheels, including CUDA packages
├── triton/                     # compiled Triton kernels, including GDN kernels
├── torchinductor/              # torch.compile artifacts
└── runs/<timestamp>/
    ├── adapter/                # LoRA adapter and tokenizer (not committed)
    └── manifest.json           # timing, VRAM, versions, sample output
```

All four caches are mounted into every container, so repeated runs avoid
re-downloading Hugging Face weights and large wheels such as `nvidia_cublas`,
and avoid recompiling Gated DeltaNet kernels. The 27B runs use the same root
with `glab27b-check-*` and `glab27b-train-*` directory prefixes.
