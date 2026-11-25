#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

lang="${GLAB_EVAL_LANG:-en}"
case "$lang" in
  en)
    export GLAB_EVAL_TASKS="${GLAB_EVAL_TASKS:-tasks.jsonl}"
    suite="baseline"
    ;;
  ru)
    export GLAB_EVAL_TASKS="${GLAB_EVAL_TASKS:-tasks.ru.jsonl}"
    suite="baseline-ru"
    ;;
  *)
    echo "GLAB_EVAL_LANG must be en or ru, got $lang" >&2
    exit 1
    ;;
esac

uv run python validate_tasks.py

output=$(uv run python run_eval.py --suite "$suite" "$@")
printf '%s\n' "$output"

run_id=$(printf '%s\n' "$output" | sed -n 's/^run_id=\([^ ]*\).*/\1/p' | tail -n 1)
if [[ -z "$run_id" ]]; then
  echo "Could not determine run_id" >&2
  exit 1
fi

if [[ -f "results/$run_id/manifest.json" ]]; then
  uv run python score.py --run-dir "results/$run_id"
fi
