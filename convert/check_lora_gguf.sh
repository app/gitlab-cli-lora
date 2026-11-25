#!/usr/bin/env bash
# Probe the Unsloth runtime image and the frozen adapter before conversion.
set -euo pipefail

log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }

ADAPTER_DIR="${ADAPTER_DIR:?ADAPTER_DIR is required}"
BASE_DIR="${BASE_DIR:-}"

log "phase=adapter"
test -d "$ADAPTER_DIR" || { log "error adapter directory is missing: $ADAPTER_DIR"; exit 1; }
for file in adapter_config.json adapter_model.safetensors tokenizer_config.json chat_template.jinja; do
  test -f "$ADAPTER_DIR/$file" || { log "error adapter file is missing: $file"; exit 1; }
  sha256sum "$ADAPTER_DIR/$file"
done

if [[ -n "$BASE_DIR" ]]; then
  log "phase=base-config"
  test -f "$BASE_DIR/config.json" || { log "error base config.json is missing: $BASE_DIR"; exit 1; }
  grep -E '"(architectures|model_type|num_hidden_layers)"' "$BASE_DIR/config.json" || true
fi

PY=/opt/unsloth-venv/bin/python3
[[ -x "$PY" ]] || PY="$(command -v python3)"
log "phase=python path=$PY"
"$PY" --version
"$PY" - <<'PY'
import importlib
for name in ("torch", "transformers", "safetensors", "huggingface_hub", "gguf"):
    try:
        module = importlib.import_module(name)
        version = getattr(module, "__version__", "unknown")
        print(f"{name}={version}")
    except Exception as exc:
        print(f"{name}=MISSING ({exc.__class__.__name__})")
PY

log "phase=converter"
CONVERTER="${CONVERTER:-}"
if [[ -z "$CONVERTER" ]]; then
  for candidate in \
    /opt/unsloth/llama.cpp/convert_lora_to_gguf.py \
    /opt/unsloth/convert_lora_to_gguf.py \
    /opt/llama.cpp/convert_lora_to_gguf.py; do
    if [[ -f "$candidate" ]]; then
      CONVERTER="$candidate"
      break
    fi
  done
fi
if [[ -f "$CONVERTER" ]]; then
  log "converter=$CONVERTER"
  "$PY" "$CONVERTER" --help | head -40
else
  log "error convert_lora_to_gguf.py not found in the image"
  exit 1
fi

log "phase=llama-server"
LLAMA_SERVER="${LLAMA_SERVER:-/opt/unsloth/llama.cpp/llama-server}"
if [[ -x "$LLAMA_SERVER" ]]; then
  "$LLAMA_SERVER" --help 2>&1 | grep -E -- '--lora|lora-init-without-apply' || true
else
  log "warning llama-server not found at $LLAMA_SERVER"
fi

log "phase=done"
