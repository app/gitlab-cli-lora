# Training brief — shell27b-ru-20261125T120604Z-044ff59a-r1

Overall pass rate: 0.9737

## Priority slices

### wrong_repo_target-api (priority 1)

Fix wrong repo target failures in api tasks

- `glab api --method GET "projects/org%2Fproject/issues/539076"` ← Получи work item 539076 из org/project через issues, а не work_items.

## Constraints

- Native Qwen3.8 XML tool-call targets (`qwen3_5_native_xml`).
- `reasoning_effort=low`.
- No glab command is ever executed.

Control tasks: 37; stable failures: 1; flaky: 0.
