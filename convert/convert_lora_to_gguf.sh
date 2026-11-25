#!/usr/bin/env bash
# Convert the frozen glab PEFT adapter into a llama.cpp GGUF LoRA file.
set -euo pipefail

log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }

ADAPTER_DIR="${ADAPTER_DIR:?ADAPTER_DIR is required}"
BASE_DIR="${BASE_DIR:?BASE_DIR is required}"
OUTPUT_FILE="${OUTPUT_FILE:?OUTPUT_FILE is required}"
MANIFEST_FILE="${MANIFEST_FILE:?MANIFEST_FILE is required}"
OUTTYPE="${OUTTYPE:-q8_0}"
RUN_NAME="${RUN_NAME:-glab27b-gguf}"
ADAPTER_RUN="${ADAPTER_RUN:-}"
TEMPLATE_SRC="${TEMPLATE_SRC:-}"
TEMPLATE_DST="${TEMPLATE_DST:-}"
TRUST_REMOTE_CODE="${TRUST_REMOTE_CODE:-0}"

test -f "$ADAPTER_DIR/adapter_config.json" || { log "error adapter_config.json is missing"; exit 1; }
test -f "$ADAPTER_DIR/adapter_model.safetensors" || { log "error adapter_model.safetensors is missing"; exit 1; }
test -f "$BASE_DIR/config.json" || { log "error base config.json is missing: $BASE_DIR"; exit 1; }

PY=/opt/unsloth-venv/bin/python3
[[ -x "$PY" ]] || PY="$(command -v python3)"

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
[[ -n "$CONVERTER" && -f "$CONVERTER" ]] || { log "error convert_lora_to_gguf.py not found"; exit 1; }

mkdir -p "$(dirname "$OUTPUT_FILE")" "$(dirname "$MANIFEST_FILE")"
log "phase=convert adapter=$ADAPTER_DIR base=$BASE_DIR outtype=$OUTTYPE converter=$CONVERTER"

# The training base is a bnb-4bit checkpoint. The converter does not need base
# weights for LoRA export, but its quantiser is triggered by quantization_config.
# Strip that field from a temporary copy of the config files.
CLEAN_BASE="$(mktemp -d "${TMPDIR:-/tmp}/lora-base-config.XXXXXX")"
trap 'rm -rf "$CLEAN_BASE"' EXIT
CLEAN_BASE="$CLEAN_BASE" BASE_DIR="$BASE_DIR" "$PY" - <<'PY'
import json
import os
import shutil
from pathlib import Path

source = Path(os.environ["BASE_DIR"])
target = Path(os.environ["CLEAN_BASE"])


def strip_quantization(value):
    if isinstance(value, dict):
        value.pop("quantization_config", None)
        for item in value.values():
            strip_quantization(item)
    elif isinstance(value, list):
        for item in value:
            strip_quantization(item)


for path in source.iterdir():
    if path.is_file() and path.suffix == ".json":
        shutil.copyfile(path, target / path.name)
config_path = target / "config.json"
config = json.loads(config_path.read_text(encoding="utf-8"))
strip_quantization(config)
config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
PY

args=(--base "$CLEAN_BASE" --outfile "$OUTPUT_FILE" --outtype "$OUTTYPE")
[[ "$TRUST_REMOTE_CODE" == "1" ]] && args+=(--trust-remote-code)
"$PY" "$CONVERTER" "${args[@]}" "$ADAPTER_DIR"

[[ -s "$OUTPUT_FILE" ]] || { log "error converter produced an empty file"; exit 1; }

if [[ -n "$TEMPLATE_SRC" && -n "$TEMPLATE_DST" ]]; then
  mkdir -p "$(dirname "$TEMPLATE_DST")"
  cp "$TEMPLATE_SRC" "$TEMPLATE_DST"
  log "chat template copied to $TEMPLATE_DST"
fi

log "phase=manifest"
OUTTYPE="$OUTTYPE" RUN_NAME="$RUN_NAME" ADAPTER_RUN="$ADAPTER_RUN" \
ADAPTER_DIR="$ADAPTER_DIR" BASE_DIR="$BASE_DIR" CONVERTER="$CONVERTER" \
OUTPUT_FILE="$OUTPUT_FILE" MANIFEST_FILE="$MANIFEST_FILE" PYTHON_BIN="$PY" \
"$PY" - <<'PY'
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


out = Path(os.environ["OUTPUT_FILE"])
adapter = Path(os.environ["ADAPTER_DIR"])
manifest = {
    "run_name": os.environ["RUN_NAME"],
    "created_at": datetime.now(timezone.utc).isoformat(),
    "adapter_run": os.environ["ADAPTER_RUN"],
    "adapter_dir": str(adapter),
    "adapter_files": {
        path.name: sha256(path)
        for path in sorted(adapter.iterdir())
        if path.is_file() and not path.name.startswith(".")
    },
    "base_config_dir": os.environ["BASE_DIR"],
    "base_config_quantization_stripped": True,
    "converter": os.environ["CONVERTER"],
    "python": os.environ["PYTHON_BIN"],
    "outtype": os.environ["OUTTYPE"],
    "output_file": str(out),
    "output_name": out.name,
    "output_sha256": sha256(out),
    "output_bytes": out.stat().st_size,
    "versions": {},
}
for name in ("torch", "transformers", "safetensors", "huggingface_hub", "gguf"):
    try:
        module = __import__(name)
        manifest["versions"][name] = getattr(module, "__version__", "unknown")
    except Exception:
        manifest["versions"][name] = "unavailable"
Path(os.environ["MANIFEST_FILE"]).write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
print(json.dumps(manifest, indent=2, sort_keys=True))
PY

log "phase=done output=$OUTPUT_FILE"
