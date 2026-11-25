# Agent guide

You are looking at a working example of turning a local 27B model into a
reliable GitLab `glab` command generator: a frozen text-only benchmark, SFT
datasets for two serving contracts, Unsloth QLoRA training, vLLM evaluation,
GGUF conversion and serving. The repository is written to be operated by an
agent; the human README only points here.

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

Training needs a GPU. Do not plan it before the datasets validate and the
benchmark baseline is reproduced.

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

Verify with `nvidia-smi` and `podman info` or `docker info`. With a socket
mounted, GPU containers can be launched from inside the agent container; the
workflows in this repository assume exactly that setup.

## Pipeline

1. **Benchmark** — `glab-eval/` holds the frozen 38-task suite, source
   snapshots and baseline results. Evaluation is text-only: the harness never
   executes a `glab` command.
2. **Datasets** — `train/data/` holds the task datasets in two contracts
   (`glab` for the frozen benchmark, `shell` for the production OpenCode tool),
   the URL-entity family and the lean ext family. Specs are committed next to
   each family; generated files rebuild byte-identically.
3. **Training** — `train/train_27b.py` (Unsloth QLoRA) rendered with the frozen
   chat template. `check` mode validates parity and token lengths before a
   multi-hour run.
4. **Evaluation** — `lora-eval/` serves the adapter on vLLM and scores the same
   frozen tasks; `compare.py` produces the baseline-versus-adapter report.
5. **Conversion and serving** — `convert/` turns the PEFT adapter into a
   llama.cpp GGUF LoRA for serving next to the base GGUF.

## Layout

- `glab-eval/` — frozen benchmark, tasks (EN/RU), docs snapshots, harness.
- `lora-eval/` — adapter endpoint config, evals and probe artifacts.
- `train/` — datasets, builder, validator, training script.
- `convert/` — PEFT-to-GGUF conversion.
- `docs/` — pipeline, runtime and serving handoff notes.
- `.forgejo/workflows/` — reference CI pipelines for a GPU host; adapt them to
  your own forge rather than copying them verbatim.

## Rules

- Frozen artifacts (tasks, docs snapshots, chat template) must not be edited;
  new evaluation tasks go into separate files.
- Generated datasets are rebuilt from specs; never hand-edit them.
- SFT targets are read-only commands. Mutating commands, GraphQL targets and
  the `work_items` API endpoint are rejected by the validator.
- Held-out rows are never trained; the validator fails on leakage.
