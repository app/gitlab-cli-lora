# Training brief — lora27b-ru-20261125T114122Z-044ff59a-r1

Overall pass rate: 0.9649

## Priority slices

### wrong_command-error (priority 2)

Fix wrong command failures in error tasks

- `glab api --method GET "search?scope=issues&search=<query>" | jq '.[] | {iid, title}'` ← Найди задачи через scope=issues и извлеки заголовки через jq, без --jq.

### wrong_repo_target-error (priority 1)

Fix wrong repo target failures in error tasks

- `glab api --method GET "search?scope=issues&search=<query>" | jq '.[] | {iid, title}'` ← Найди задачи через scope=issues и извлеки заголовки через jq, без --jq.

### flaky-needs-review (priority 3)

Manually review unstable tasks before adding them to training data


## Constraints

- Native Qwen3.8 XML tool-call targets (`qwen3_5_native_xml`).
- `reasoning_effort=low`.
- No glab command is ever executed.

Control tasks: 36; stable failures: 1; flaky: 1.
