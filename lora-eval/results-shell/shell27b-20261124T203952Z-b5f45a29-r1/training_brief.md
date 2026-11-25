# Training brief — shell27b-20261124T203952Z-b5f45a29-r1

Overall pass rate: 0.9035

## Priority slices

### wrong_command-error (priority 2)

Fix wrong command failures in error tasks

- `glab api --method GET "search?scope=issues&search=<query>" | jq '.[] | {iid, title}'` ← Search issues with scope=issues and filter their titles with jq, without using a --jq flag on glab api.

### wrong_repo_target-api (priority 1)

Fix wrong repo target failures in api tasks

- `glab api --method GET "projects/org%2Fproject/issues/539076"` ← Read work item 539076 from org/project through the issues REST API, not the work_items endpoint.

### wrong_repo_target-issue (priority 1)

Fix wrong repo target failures in issue tasks

- `glab issue list --per-page 10` ← List 10 open issues per page in the current project.

### flaky-needs-review (priority 3)

Manually review unstable tasks before adding them to training data


## Constraints

- Native Qwen3.8 XML tool-call targets (`qwen3_5_native_xml`).
- `reasoning_effort=low`.
- No glab command is ever executed.

Control tasks: 33; stable failures: 3; flaky: 2.
