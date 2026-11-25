# Run the pipeline without CI

Run this file when the normal path is unavailable: the repository's operational
docs ([`training-runtime.md`](training-runtime.md)) drive every stage through
Forgejo Actions, and you have no Forgejo — only a GPU on the host and yourself
inside an [OpenCode container](https://github.com/app/opencode-python). Nothing
here needs the CI: each stage is the same container the workflow would start,
launched by hand.

The goal is a trained adapter inside the working directory, plus its manifest,
and a path you can hand back to the user. Budget roughly 30 GB of downloads and
2-4 hours of GPU time to get there; scoring adds about 30 GB more (§9).

## 1. Cold start

The container's project directory may be empty: there is nothing to `git
remote -v` yet. Clone the repository the user linked you — published as
[`app/gitlab-cli-lora`](https://github.com/app/gitlab-cli-lora), public, so an
anonymous HTTPS clone needs no credential — then work from its root and read the
agent guide:

```sh
git clone https://github.com/app/gitlab-cli-lora.git
cd gitlab-cli-lora
```

Derive every path from that point, never hardcode it:

```sh
REPO=$(git rev-parse --show-toplevel)
```

The snippets below are bash and assume one continuous shell: `$REPO`,
`$HOST_REPO`, `$ART_ROOT` and `$TRAIN_IMAGE` have to survive from section to
section, so re-export them in a fresh call.

## 2. Does this environment have a GPU?

The training container does not run inside your container: it is created by the
host's container engine, through its socket, and gets its GPU from the host. So
**your own container does not need a GPU device**, and a missing `nvidia-smi` or
`/dev/nvidia0` inside it is normal, not a failure. What you need is the socket.

Check, in order:

```sh
test -S /run/podman/podman.sock || test -S /var/run/docker.sock || echo "no runtime socket"
command -v podman docker || echo "no container client"
```

**No socket.** You cannot launch anything, and no amount of installing fixes
it. Stop and ask the user to relaunch the OpenCode container with the runtime
socket, from the same host directory as before — otherwise the workspace and
the clone are lost. For the Python image on rootless Podman:

```sh
podman run -it --rm --userns=keep-id:uid=1000,gid=1000 \
  --name "opencode-$$" \
  -v "$PWD:/home/opencode/projects/$(basename "$PWD")" \
  -v "opencode-python-state-$(id -un):/home/opencode/.local" \
  -v "/run/user/$(id -u)/podman/podman.sock:/run/podman/podman.sock" \
  -e CONTAINER_HOST=unix:///run/podman/podman.sock \
  -e HF_TOKEN \
  --detach-keys="ctrl-],ctrl-q" \
  ghcr.io/app/opencode-python:latest
```

For rootful Podman mount `/run/podman/podman.sock` instead, and for Docker use
`--user "$(id -u):$(id -g)"` with `-v /var/run/docker.sock:/var/run/docker.sock`.
Swap in the TypeScript image and its state volume for that flavour.

**Socket present, client missing.** Install it yourself; the container grants
passwordless sudo:

```sh
cat /etc/os-release          # pick the line below
sudo apk add --no-cache podman-remote      # Alpine
sudo apt-get install -y podman-remote      # Debian, Ubuntu
export CONTAINER_HOST=unix:///run/podman/podman.sock
podman info --format '{{.Host.OCIRuntime.Name}}'
```

The install lasts until the container exits, which is fine for one run. If only
`/var/run/docker.sock` is mounted, install `docker-cli` instead and everything
below reads `docker` where it says `podman`.

**Verify the GPU where it is used.** Ask the training image itself, and keep the
image name in a variable — the training runs use the same one, so the pull is
paid once into the host image store:

```sh
TRAIN_IMAGE=docker.io/pytorch/pytorch:2.15.0-cuda13.2-cudnn9-runtime
podman run --rm --device nvidia.com/gpu=all "$TRAIN_IMAGE" \
  nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader
```

If it fails, the host has no usable GPU: report that and stop. Do not install
drivers, and never fall back to CPU training — the 27B does not fit.

## 3. One mounted path, everything inside it

Because the job container is created by the host engine, every bind-mount source
must be a **host** path. A path that only exists inside your own container means
nothing to the engine: the job would start with an empty directory and fail
somewhere far away. The one host path you can rely on is the directory the user
launched the OpenCode container from, so print your own mounts and translate the
workspace path into its host copy:

```sh
SELF=$(podman ps --format '{{.ID}}' | grep -m1 "^$(hostname)")   # this container
podman inspect "$SELF" --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
```

Look for the line whose destination is your workspace or a parent of it. In a
cold-start workspace the clone sits inside that mount, so `$HOST_REPO` is the
source with the clone's subdirectory appended (`hostname` is the container id, so
`$SELF` is this container unless the user overrode `--hostname`; if the match is
empty, select the OpenCode container by name). Mechanically:

```sh
HOST_REPO=$(podman inspect "$SELF" \
  --format '{{range .Mounts}}{{.Destination}}\t{{.Source}}{{"\n"}}{{end}}' \
  | awk -F'\t' -v r="$REPO" 'index(r "/", $1 "/") == 1 && length($1) > n {
      n = length($1); src = $2 } END { if (n) print src substr(r, n + 1) }')
echo "HOST_REPO=$HOST_REPO"
```

Prove the path before trusting it — the job reads and writes only through it:

```sh
podman run --rm -v "$HOST_REPO:/probe:ro" docker.io/library/busybox:latest ls /probe
```

Everything the pipeline touches belongs under `$HOST_REPO`, so nothing escapes the
workspace and nothing can be committed by accident — `/tmp/` is already in
`.gitignore`:

```sh
ART_ROOT=$HOST_REPO/tmp/artifacts
GPU_LOCK=$HOST_REPO/tmp/gpu.lock
mkdir -p "$ART_ROOT"/{runs,hf,pip-cache,triton,torchinductor}
```

On SELinux hosts (Fedora, RHEL, openSUSE) add `:z` to every bind mount, or the
container will see empty directories.

## 4. The GPU is a single resource

One RTX 5090 D v2, 24 GiB, and both training and any serving stack need all of
it. Before starting, look:

```sh
podman ps --format '{{.Names}} {{.Status}}'
podman run --rm --device nvidia.com/gpu=all "$TRAIN_IMAGE" \
  nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader
```

If memory is already in use — usually vLLM serving a model — ask the user to
stop it and wait. Do not kill someone else's container, and do not try to learn
how the serving stack is managed: freeing the GPU is the user's call. Then take a
lock so two of your own runs cannot collide:

```sh
exec 9>>"$GPU_LOCK"
flock -n 9 || { echo "gpu lock held"; exit 1; }
```

Keep that shell alive for the whole job: the lock belongs to the file descriptor,
so a shell that exits releases it while the container is still training.

## 5. Datasets (no GPU needed)

Datasets are generated from committed specs, and the generated files rebuild
byte-identically:

```sh
cd "$REPO"
for lang in en ru; do
  uv run --project train python train/build_dataset.py --family tasks --shape glab  --lang "$lang"
  uv run --project train python train/build_dataset.py --family tasks --shape shell --lang "$lang"
  uv run --project train python train/build_dataset.py --family url   --shape glab  --lang "$lang"
  uv run --project train python train/build_dataset.py --family url   --shape shell --lang "$lang"
  uv run --project train python train/build_dataset.py --family ext   --shape shell --lang "$lang"
done
uv run --project train python train/validate_dataset.py --lang all
```

Expected tail of the validator, which is also the row budget for the run below:

```text
OK 1056 examples across 10 datasets
  eval prompt collisions: 0
  native XML targets: 100%
```

The only expected diff after a rebuild is the `created_at` stamp in each
`dataset_manifest.json`; restore those, and never edit a generated file.

## 6. Parity check before training

`TRAIN_MODE=check` loads the tokenizer only — no 22 GB weights, no GPU memory —
and proves the frozen chat template reproduces every stored row byte for byte and
that no row exceeds the sequence length. It still needs the GPU device, because
`train/run_train_27b.sh` asserts CUDA visibility before anything else. Expect a
few minutes once the pinned Python stack is cached; the first run also pulls the
image and installs that stack, so budget 10-15 minutes.

```sh
RUN_NAME="glab27b-check-$(date -u +%Y%m%dT%H%M%SZ)"
TRAIN_MIX=tasks/glab/en,tasks/glab/ru,tasks/shell/en,tasks/shell/ru,url/glab/en,url/glab/ru,url/shell/en,url/shell/ru,ext/shell/en,ext/shell/ru

podman run --rm \
  --device nvidia.com/gpu=all \
  -v "$HOST_REPO:/workspace/src:rw" \
  -v "$ART_ROOT:/workspace/artifacts:rw" \
  -v "$ART_ROOT/hf:/workspace/.cache/huggingface:rw" \
  -v "$ART_ROOT/pip-cache:/workspace/.cache/pip:rw" \
  -v "$ART_ROOT/triton:/workspace/.triton:rw" \
  -v "$ART_ROOT/torchinductor:/workspace/.torchinductor:rw" \
  -e HF_HOME=/workspace/.cache/huggingface \
  -e PIP_CACHE_DIR=/workspace/.cache/pip \
  -e TRITON_CACHE_DIR=/workspace/.triton/cache \
  -e TORCHINDUCTOR_CACHE_DIR=/workspace/.torchinductor \
  -e HF_XET_HIGH_PERFORMANCE=1 \
  -e PYTHONUNBUFFERED=1 \
  -e TOKENIZERS_PARALLELISM=false \
  -e HF_TOKEN="${HF_TOKEN:-}" \
  -e HUGGING_FACE_HUB_TOKEN="${HF_TOKEN:-}" \
  -e TRAIN_MODE=check \
  -e TRAIN_MODEL=unsloth/Qwen3.8-27B-unsloth-bnb-4bit \
  -e TRAIN_MIX="$TRAIN_MIX" \
  -e TRAIN_MAX_SEQ_LENGTH=8192 \
  -e ARTIFACTS_DIR="/workspace/artifacts/runs/$RUN_NAME" \
  -w /workspace/src \
  "$TRAIN_IMAGE" \
  bash train/run_train_27b.sh 2>&1 | tee "$ART_ROOT/runs/$RUN_NAME.log"
```

The image is about 3.3 GB compressed, 10 GB on disk; the first run also installs
a pinned Python stack. Both land in the caches above and are reused.
`ARTIFACTS_DIR` has no usable default outside CI, so always set it. Neither base
model is gated today, so `HF_TOKEN` may go unused; pass it through anyway, since
a token-gated mirror or a model swap will need it.

Do not start training until this passes.

## 7. Train

Same container, same mounts, plus `TRAIN_MODE=train`, a step count and
`PYTORCH_CUDA_ALLOC_CONF`. Shell-shape rows carry the ~6k-token frozen OpenCode
prompt, so `TRAIN_MAX_SEQ_LENGTH=8192` is mandatory — the frozen glab-only runs
used 1024 and would silently truncate. Steps follow from the mix size: with
`TRAIN_BATCH_SIZE=1` and `TRAIN_GRAD_ACCUM=4` one step consumes 4 rows, so 1056
rows are 264 steps per epoch and `528` is two epochs. The first training run also
downloads about 22 GB of 4-bit weights into `$ART_ROOT/hf`.

```sh
RUN_NAME="glab27b-train-$(date -u +%Y%m%dT%H%M%SZ)"

podman run --rm \
  --device nvidia.com/gpu=all \
  -v "$HOST_REPO:/workspace/src:rw" \
  -v "$ART_ROOT:/workspace/artifacts:rw" \
  -v "$ART_ROOT/hf:/workspace/.cache/huggingface:rw" \
  -v "$ART_ROOT/pip-cache:/workspace/.cache/pip:rw" \
  -v "$ART_ROOT/triton:/workspace/.triton:rw" \
  -v "$ART_ROOT/torchinductor:/workspace/.torchinductor:rw" \
  -e HF_HOME=/workspace/.cache/huggingface \
  -e PIP_CACHE_DIR=/workspace/.cache/pip \
  -e TRITON_CACHE_DIR=/workspace/.triton/cache \
  -e TORCHINDUCTOR_CACHE_DIR=/workspace/.torchinductor \
  -e HF_XET_HIGH_PERFORMANCE=1 \
  -e PYTHONUNBUFFERED=1 \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e TOKENIZERS_PARALLELISM=false \
  -e HF_TOKEN="${HF_TOKEN:-}" \
  -e HUGGING_FACE_HUB_TOKEN="${HF_TOKEN:-}" \
  -e TRAIN_MODE=train \
  -e TRAIN_MODEL=unsloth/Qwen3.8-27B-unsloth-bnb-4bit \
  -e TRAIN_MIX="$TRAIN_MIX" \
  -e TRAIN_MAX_SEQ_LENGTH=8192 \
  -e TRAIN_STEPS=528 \
  -e TRAIN_LORA_R=16 \
  -e TRAIN_LORA_ALPHA=16 \
  -e TRAIN_LR=2e-4 \
  -e TRAIN_INFERENCE=1 \
  -e ARTIFACTS_DIR="/workspace/artifacts/runs/$RUN_NAME" \
  -w /workspace/src \
  "$TRAIN_IMAGE" \
  bash train/run_train_27b.sh 2>&1 | tee "$ART_ROOT/runs/$RUN_NAME.log"
```

Budget 2-4 hours for this mix. Do not read silence as a hang: the script prints a
timestamped heartbeat every 30 seconds with phase, step, loss and elapsed time,
and one line per step with `vram_peak_gib`.

### Long runs

A foreground command that lasts hours will outlive a single shell call. Start the
same container detached and wait for it in short calls instead — and note that
the GPU lock belongs to the shell that took it, so if that shell is gone the lock
is gone with it: say so when you report progress, and re-take it before starting
anything else on the GPU.

```sh
# Same flags as above, but detached: -d, --name, and no pipe to tee.
podman run -d --name "$RUN_NAME" \
  --device nvidia.com/gpu=all \
  ... \
  "$TRAIN_IMAGE" bash train/run_train_27b.sh

podman logs --tail 40 "$RUN_NAME"      # progress while it runs
podman wait "$RUN_NAME"; echo "exit=$?"
podman logs "$RUN_NAME" > "$ART_ROOT/runs/$RUN_NAME.log"
podman rm "$RUN_NAME"
```

The CI wraps the same call in `timeout 300m`; use a comparable ceiling so a stuck
job cannot hold the GPU overnight.

| Symptom                                | What it means                                                                                      |
| -------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `CUDA is not visible in the container` | the socket works, the engine gave the job no GPU; re-check `--device nvidia.com/gpu=all`           |
| `gpu lock held`                        | another run of yours holds `$GPU_LOCK`                                                             |
| loss `NaN` in the first steps          | do not force a dtype: Unsloth keeps the Qwen GDN layers in float32 for exactly this reason         |
| out of memory                          | confirm nothing else is on the GPU, then shrink the mix; never drop `TRAIN_BATCH_SIZE` below 1     |
| `token_length_over_max_seq` above zero | a row does not fit `TRAIN_MAX_SEQ_LENGTH` and `check` fails fast — the mix is wrong, not the limit |

Only the adapter and the tokenizer files are saved, never the base weights.

## 8. Result

```sh
RUN_DIR="$ART_ROOT/runs/$RUN_NAME"
cat "$RUN_DIR/manifest.json"
ls -l "$RUN_DIR/adapter"
sha256sum "$RUN_DIR/adapter"/* > "$ART_ROOT/runs/$RUN_NAME.adapter.sha256"   # confirm vs manifest
grep -E 'train metric|adapter saved|vram_peak_gib' "$ART_ROOT/runs/$RUN_NAME.log" | tail -5
git -C "$REPO" status --short   # only the expected dataset `created_at` stamps
```

The manifest records the mix, `max_seq_length`, `max_steps`, LoRA rank and
alpha, `elapsed_seconds`, `vram_peak_gib`, `adapter_sha256` and the versions of
the pinned stack — and its `adapter_dir` is the **container** path
(`/workspace/artifacts/...`). Report the host path instead.

In one message to the user: `$ART_ROOT/runs/$RUN_NAME/adapter` as the host sees
it, the mix and sequence length, steps and duration, peak VRAM, the final loss
from the log, and where the checksum file and the run log are. Nothing else
leaves the host: git stores logs and metadata only, never weights.

## 9. Next steps

- Score the adapter against the frozen 38 tasks:
  [`lora-eval/README.md`](../lora-eval/README.md) and
  [`compare.py`](../compare.py). Expect roughly 30 GB more — the vLLM image and
  the base model it serves the adapter on. The harness talks to an OpenAI
  endpoint; from inside this container `http://127.0.0.1:8000/v1` is the
  container's own loopback, so point `GLAB_EVAL_ENDPOINT` at the published host
  address.
- Convert the adapter for llama.cpp with [`convert/`](../convert) and hand it
  over as described in [the serving handoff](llm-server-lora-handoff.md).

## Traps

- An empty project directory is the normal start: clone first, then read
  `AGENTS.md`.
- The runtime socket is the only GPU blocker. Your own container needs no GPU
  device; the job container gets it from the host.
- Bind mounts go through the host engine: mount `$HOST_REPO`, never a path that
  exists only inside your container. SELinux needs `:z`.
- `ARTIFACTS_DIR` defaults to a container path that does not exist outside CI.
- `TRAIN_MAX_SEQ_LENGTH=8192` for shell-shape rows; 1024 silently truncates the
  frozen OpenCode prompt.
- Run `TRAIN_MODE=check` before every `train`.
- Pass `HF_TOKEN` through with `-e HF_TOKEN="${HF_TOKEN:-}"`; never echo it and
  never write it into a committed file.
- Frozen artifacts (`glab-eval/**`, `train/data/contracts/**`, the chat
  template) are read-only in practice; new evaluation tasks go into separate
  files.
