# Frozen OpenCode serving contract

Snapshot of the exact request shape OpenCode sends to the production model
profile `local-unsloth/qwen3.8-27b-glab27b` (the GGUF `q8_0` glab adapter
served through llama.cpp on the GPU host). Shell-shape training data and the
harness `shell` eval mode render against these bytes, so the adapter is
trained and scored under the prompt prefix it actually sees.

Captured 2026-11-24 with OpenCode `v2.4.1` (the container image build):
a throwaway fake `openai-compatible` provider logged one main-agent request
body (`opencode run --standalone` in a scratch directory); the global config
`AGENTS.md` and provider list are the container defaults. No secrets: the
body carries no headers, no API keys, and the session had no project data.

## Files

| File                    | Content                                                                 |
| ----------------------- | ----------------------------------------------------------------------- |
| `capture-request.json`  | Raw `chat/completions` request body, verbatim (14 tools, full payload). |
| `system-prompt.raw.txt` | `messages[0].content` of the capture, verbatim (capture model card).    |
| `system-prompt.txt`     | Training/eval variant: same text with the `# Your Model` block replaced |
|                         | by the production card (`local-unsloth/qwen3.8-27b-glab27b`).           |
| `shell-tool.json`       | The `shell` tool entry of the capture `tools` array, pretty-printed.    |

SHA256 of every file is recorded in each shell dataset manifest
(`train/data/shell/*/dataset_manifest.json`).

## Known drift (accepted)

- The `Today's date` line and the session-specific tail of the system prompt
  (skills list, Code Mode tool catalog) reflect this container's config at
  capture time, not per-session variation. Production sessions see the same
  global `AGENTS.md` and the same OpenCode install, so drift is limited to
  dates and per-session extras.
- The live payload sends all enabled tools (14 at capture). Shell-shape
  training and eval render with `shell` only, to fit the training sequence
  budget; `glab-eval/probe_opencode_payload.py` replays the **full** frozen
  tool list from `capture-request.json` against the served endpoint as the
  multi-tool selection check.

## Refresh procedure

Required when the OpenCode version, the global `~/.config/opencode` config,
or the tool set changes materially:

1. Re-capture with the fake provider (see commit that added this directory
   for the exact recipe) and rewrite the four files above.
2. Rebuild shell datasets: `python3 train/build_dataset.py --shape shell --lang en`
   (and `--lang ru`), then `python3 train/validate_dataset.py`.
3. Re-run the shell eval suites; new numbers are comparable only after a full
   re-baseline.
