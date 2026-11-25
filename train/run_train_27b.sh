#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"
}

log "phase=container-start"
python - <<'PY'
import torch
print("torch", torch.__version__, "cuda", torch.version.cuda)
assert torch.cuda.is_available(), "CUDA is not visible in the container"
print("gpu", torch.cuda.get_device_name(0))
PY

# The PyTorch image uses a system-managed Python; the container is disposable,
# so installing into it directly is safe. Versions are pinned to keep the
# renderer and QLoRA stack reproducible between check and train runs.
log "phase=pip-install"
python -m pip install --break-system-packages \
  torch==2.14.1 \
  transformers==5.17.0 \
  datasets==4.3.0 \
  trl==0.22.2 \
  protobuf==3.20.3 \
  unsloth==2026.11.9 \
  unsloth_zoo==2026.11.8
python -m pip install --break-system-packages --no-deps transformers-cfg

log "phase=python"
python train/train_27b.py
log "phase=done"
