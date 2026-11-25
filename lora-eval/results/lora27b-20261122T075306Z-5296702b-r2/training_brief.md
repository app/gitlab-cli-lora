# Training brief — lora27b-20261122T075306Z-5296702b-r2

Overall pass rate: 0.8596

## Priority slices

### invalid_flag-error (priority 2)

Fix invalid flag failures in error tasks

- `glab issue list` ← Show open issues. The user suggested --state opened; give the correct glab command instead.

### wrong_command-error (priority 2)

Fix wrong command failures in error tasks

- `glab api --method GET "search?scope=issues&search=<query>" | jq '.[] | {iid, title}'` ← Search issues with scope=issues and filter their titles with jq, without using a --jq flag on glab api.

### wrong_repo_target-api (priority 1)

Fix wrong repo target failures in api tasks

- `glab api --method GET "projects/org%2Fproject/issues/539076"` ← Read work item 539076 from org/project through the issues REST API, not the work_items endpoint.

### no_tool_call-api (priority 1)

Fix no tool call failures in api tasks

- `glab api --method GET "projects/org%2Fproject/issues/539076"` ← Read work item 539076 from org/project through the issues REST API, not the work_items endpoint.

### flaky-needs-review (priority 3)

Manually review unstable tasks before adding them to training data


## Constraints

- Native Qwen3.8 XML tool-call targets (`qwen3_5_native_xml`).
- `reasoning_effort=low`.
- No glab command is ever executed.

Control tasks: 29; stable failures: 3; flaky: 6.
