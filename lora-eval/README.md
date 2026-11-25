# LoRA evaluation suite

`glab-eval` stays frozen as the stage-zero diagnostic baseline. This directory
configures the same harness for the trained QLoRA adapter, served by vLLM as a
LoRA module next to the unchanged base model.

`config.yaml` differs from `glab-eval/config.yaml` only in the endpoint:

- `base_url: http://127.0.0.1:8000/v1` — the workflow runs the harness with
  `--network=host`, so localhost reaches the published vLLM port reliably;
- `model_id: glab27b` — the name passed to vLLM's `--lora-modules`;
- `model_root: /workspace/adapter` — the container path of the adapter mount.

Tasks, source snapshots, the chat template, tool schema, generation settings,
and scoring are still loaded from the frozen `glab-eval` directory. The harness
writes temporary runs to `glab-eval/results/`, then the workflow copies them to
`lora-eval/results/` and commits them to `main`, next to but never inside
`glab-eval/results/`. Each run directory contains `manifest.json`,
`responses.jsonl`, `failures.jsonl`, `stability.json`, `metrics.json`,
`training_handoff.json`, `training_brief.md`, and `report.md`; the shared
`aggregate.json` and `index.json` sit at the top of `lora-eval/results/`.

Run through the workflow (Forgejo Actions); without Forgejo, the same containers
come up by hand as described in [`../docs/run-without-ci.md`](../docs/run-without-ci.md):

```sh
# Serving smoke test only.
curl -fsS -X POST \
  -H "Authorization: token $FORGEJO_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FORGEJO_URL/api/v1/repos/ai/qwen38-27b-lora/actions/workflows/eval-lora.yaml/dispatches" \
  -d '{"ref":"main","inputs":{"action":"check"},"return_run_info":true}'

# Three independent evaluation runs plus aggregation.
curl -fsS -X POST \
  -H "Authorization: token $FORGEJO_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FORGEJO_URL/api/v1/repos/ai/qwen38-27b-lora/actions/workflows/eval-lora.yaml/dispatches" \
  -d '{"ref":"main","inputs":{"action":"eval"},"return_run_info":true}'

# Re-score/aggregate existing runs without starting vLLM.
curl -fsS -X POST \
  -H "Authorization: token $FORGEJO_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FORGEJO_URL/api/v1/repos/ai/qwen38-27b-lora/actions/workflows/eval-lora.yaml/dispatches" \
  -d '{"ref":"main","inputs":{"action":"score"},"return_run_info":true}'
```

The workflow holds the GPU lock, stops the vLLM container on exit, publishes
results to `main` under `lora-eval/results/`, and keeps the detailed
`ci-action.log` in the separate `ci/lora-eval-report` branch. Harness containers
run as the host user with `--userns=keep-id --user "$(id -u):$(id -g)"` and
install `httpx`/`pyyaml` with `pip --user` into a throwaway `HOME`, so no
root-owned files are written into the mounted workspace. `keep-id` is required
because plain rootless Podman would map that numeric UID to a subuid and break
writes to the workspace. The vLLM container keeps the image default user, which
rootless Podman maps to the workspace owner.
