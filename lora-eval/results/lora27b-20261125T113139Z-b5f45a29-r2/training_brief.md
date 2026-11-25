# Training brief — lora27b-20261125T113139Z-b5f45a29-r2

Overall pass rate: 0.9298

## Priority slices

### wrong_command-issue (priority 2)

Fix wrong command failures in issue tasks

- `glab issue list --search timeout` ← Search issues for the word timeout.

### wrong_repo_target-api (priority 1)

Fix wrong repo target failures in api tasks

- `glab api --method GET "projects/org%2Fproject/issues/539076"` ← Read work item 539076 from org/project through the issues REST API, not the work_items endpoint.

### flaky-needs-review (priority 3)

Manually review unstable tasks before adding them to training data


## Constraints

- Native Qwen3.8 XML tool-call targets (`qwen3_5_native_xml`).
- `reasoning_effort=low`.
- No glab command is ever executed.

Control tasks: 35; stable failures: 2; flaky: 1.
