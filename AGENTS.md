# Agent guide

You are looking at a LoRA fine-tune of a local model, done end to end on a
single 24 GiB consumer GPU. It started from a gap: the best local model of
its time (Qwen3.8-27B on an RTX 5090 D v2), driven through OpenCode, did not
know the GitLab CLI — `glab` calls failed, and `glab-errors-sessions/` is that
failure recorded. The fix lives here: a frozen text-only benchmark, SFT
datasets for both serving contracts, Unsloth QLoRA training on the same GPU,
vLLM evaluation, GGUF conversion and a serving handoff. This repository is
operated by an agent; the human README only points here.

## First move

1. Read `docs/training-runtime.md` — the pipeline, the GPU-host setup, the
   evaluation protocol and the artifact paths.
2. Read `train/data/README.md` — the dataset layout, sizes and regeneration
   commands.
3. Start with something that needs no GPU: regenerate the datasets, run the
   validator, or score an existing endpoint with the frozen benchmark.

```sh
uv run --project train python train/build_dataset.py --lang en --shape shell
uv run --project train python train/validate_dataset.py --lang all
cd glab-eval && uv run python validate_tasks.py
```

Training runs on the local GPU host — one RTX 5090 D v2, 24 GiB VRAM, shared
with vLLM serving through `/srv/containers/runner/gpu.lock`, one job at a
time. Never plan training before the datasets validate and the baseline reruns.

## GPU access from inside a container

A common failure: the agent runs in a container, `nvidia-smi` is missing or
reports no devices, but the host has a working GPU. Do not install drivers and
do not fall back to CPU training. Ask the user to relaunch the agent container
with the GPU device and the container runtime socket:

- NVIDIA CDI device (podman): `--device nvidia.com/gpu=all`
- NVIDIA device (docker): `--gpus all`
- Rootless podman socket:
  `-v /run/user/$(id -u)/podman/podman.sock:/run/podman/podman.sock`
  `-e CONTAINER_HOST=unix:///run/podman/podman.sock`
- Rootful podman socket: `-v /run/podman/podman.sock:/run/podman/podman.sock`
- Docker socket: `-v /var/run/docker.sock:/var/run/docker.sock`
- Hugging Face token for gated weights: `-e HF_TOKEN=...`

Verify with `nvidia-smi` and `podman info` or `docker info`: with the runtime
socket mounted, GPU containers launch from inside the agent container, which
is what the workflows in this repository assume.

## Pipeline

1. **Benchmark** — `glab-eval/` holds the frozen 38-task suite, its Russian
   mirror `tasks.ru.jsonl`, source snapshots and baseline results. Evaluation
   is text-only: the harness never executes a `glab` command.
2. **Error corpus** — `glab-errors-sessions/` records real `glab` failures
   from OpenCode sessions: where the project began, and where residual gaps
   are re-checked. `python3 collect.py` rewrites the snapshot; it stores no
   credentials.
3. **Datasets** — `train/data/` holds three SFT families in two contracts:
   `glab` (the synthetic benchmark tool) and `shell` (the production OpenCode
   contract, kept verbatim in `train/data/contracts/opencode/`). `tasks`
   paraphrases the 38 evaluation tasks (180 rows per language and shape),
   `url` adds URL-entity resolution (66), `ext` a command surface (36, shell
   only) — 1056 rows in the full mix, rebuilt from the committed specs.
4. **Training** — `train/train_27b.py`, launched by `train/run_train_27b.sh`
   with pinned dependencies, runs Unsloth QLoRA on the 4-bit 27B and saves
   only the adapter. `TRAIN_MODE=check` proves the frozen chat template
   reproduces every stored row byte for byte and checks token lengths without
   loading weights; `train/smoke_4b.py` is the 4B stack pre-flight.
   Shell-shape rows need `max_seq_length=8192` (frozen prompt ~6k tokens).
5. **Evaluation** — `lora-eval/` serves the adapter on vLLM and scores the
   same frozen tasks, in the benchmark contract or under the production one
   (`run_eval.py --mode shell`); `compare.py` writes the comparison against
   the baseline. `glab-eval/probe_opencode_payload.py` replays the full
   production tool set into `lora-eval/probes/`.
6. **Conversion and serving** — `convert/` turns the PEFT adapter into a
   llama.cpp GGUF LoRA next to the base GGUF; the runtime belongs to the
   `llm-server` repo, see [the handoff](docs/llm-server-lora-handoff.md).

## Layout

- `glab-eval/` — frozen benchmark, tasks (EN/RU), docs snapshots, harness.
- `glab-errors-sessions/` — collector and real `glab` error corpus.
- `train/` — datasets, builder, validator, 4B smoke and 27B training scripts.
- `lora-eval/` — adapter endpoint config, results (EN/RU, both contracts), probes.
- `convert/` — PEFT-to-GGUF conversion.
- `compare.py` — baseline-versus-adapter report from two `aggregate.json`.
- `docs/` — pipeline, runtime and serving handoff notes.
- `.forgejo/workflows/` — reference CI pipelines for a GPU host; adapt them
  to your own forge rather than copying them verbatim.

## Rules

- Frozen artifacts (tasks, docs snapshots, chat template) must not be edited;
  new evaluation tasks go into separate files.
- Generated datasets are rebuilt from specs; never hand-edit them.
- The `glab` benchmark contract stays frozen at 38 tasks: new families are
  trained in the shell shape only.
- SFT targets are read-only commands. Mutating commands, GraphQL targets and
  the `work_items` API endpoint are rejected by the validator.
- Held-out rows are never trained; the validator fails on leakage.
