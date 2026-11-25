# Training brief — lora27b-20261125T155820Z-2b69aac2-r3

Overall pass rate: 0.9474

## Priority slices

### wrong_command-error (priority 2)

Fix wrong command failures in error tasks

- `glab api --method GET "search?scope=issues&search=<query>" | jq '.[] | {iid, title}'` ← Search issues with scope=issues and filter their titles with jq, without using a --jq flag on glab api.

### wrong_repo_target-api (priority 1)

Fix wrong repo target failures in api tasks

- `glab api --method GET "projects/org%2Fproject/issues/539076"` ← Read work item 539076 from org/project through the issues REST API, not the work_items endpoint.

## Constraints

- Native Qwen3.8 XML tool-call targets (`qwen3_5_native_xml`).
- `reasoning_effort=low`.
- No glab command is ever executed.

Control tasks: 36; stable failures: 2; flaky: 0.
