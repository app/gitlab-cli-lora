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
# so installing into it directly is safe and avoids the missing ensurepip.
log "phase=pip-install"
python -m pip install --break-system-packages unsloth
python -m pip install --break-system-packages transformers==4.57.6
python -m pip install --break-system-packages --no-deps trl==0.22.2
python -m pip install --break-system-packages protobuf==3.20.3
python -m pip install --break-system-packages --no-deps transformers-cfg

log "phase=python"
python train/smoke_4b.py
log "phase=done"
