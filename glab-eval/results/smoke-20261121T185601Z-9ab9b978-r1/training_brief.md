# Training brief — smoke-20261121T185601Z-9ab9b978-r1

Overall pass rate: 0.0

## Priority slices

### invalid_flag-issue (priority 2)

Fix invalid flag failures in issue tasks

- `glab issue list --closed` ← Show only closed issues in the current project.
- `glab issue list` ← List open issues in the current project.

## Constraints

- Native Qwen3.8 XML tool-call targets (`qwen3_5_native_xml`).
- `reasoning_effort=low`.
- No glab command is ever executed.

Control tasks: 0; stable failures: 2; flaky: 0.
