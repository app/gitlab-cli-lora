# Training brief — shell27b-ru-20261124T210420Z-044ff59a-r3

Overall pass rate: 0.9474

## Priority slices

### wrong_repo_target-api (priority 1)

Fix wrong repo target failures in api tasks

- `glab api --method GET "projects/org%2Fproject/issues/539076"` ← Получи work item 539076 из org/project через issues, а не work_items.

### no_tool_call-error (priority 1)

Fix no tool call failures in error tasks

- `glab api --method GET "search?scope=issues&search=<query>" | jq '.[] | {iid, title}'` ← Найди задачи через scope=issues и извлеки заголовки через jq, без --jq.

### wrong_command-error (priority 2)

Fix wrong command failures in error tasks

- `glab api --method GET "search?scope=issues&search=<query>" | jq '.[] | {iid, title}'` ← Найди задачи через scope=issues и извлеки заголовки через jq, без --jq.

## Constraints

- Native Qwen3.8 XML tool-call targets (`qwen3_5_native_xml`).
- `reasoning_effort=low`.
- No glab command is ever executed.

Control tasks: 36; stable failures: 2; flaky: 0.
