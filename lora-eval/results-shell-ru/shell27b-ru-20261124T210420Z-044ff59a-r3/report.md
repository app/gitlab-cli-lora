# glab CLI evaluation report — shell27b-ru-20261124T210420Z-044ff59a-r3

Created: 2026-11-24T21:04:20.458781+00:00  
Suite: shell27b-ru (r3)  
Model: glab27b (/workspace/adapter)  
vLLM: 0.33.0  
Sources: glab 1.100.0, skill 1.16.2, retrieved 2026-11-21T18:52:52Z

## Headline metrics

| Metric | Value |
| --- | ---: |
| `total_responses` | 114 |
| `model_responses` | 114 |
| `infra_errors` | 0 |
| `pass_rate` | 0.9474 |
| `valid_tool_call_rate` | 0.9825 |
| `xml_parse_success_rate` | None |
| `normalized_command_match` | 0.9474 |
| `required_flags_present` | 0.9825 |
| `forbidden_absent` | 1.0 |
| `avg_latency_ms` | 8764.231 |
| `avg_reasoning_tokens` | 54.0351 |
| `avg_completion_tokens` | 88.9474 |

## Coverage by category

| Category | Responses | Pass rate | Valid tool call |
| --- | ---: | ---: | ---: |
| api | 21 | 0.8571 | 1.0 |
| ci | 15 | 1.0 | 1.0 |
| error | 9 | 0.6667 | 0.7778 |
| issue | 36 | 1.0 | 1.0 |
| mr | 27 | 1.0 | 1.0 |
| safety | 6 | 1.0 | 1.0 |

## Failures by error type

| Error type | Count |
| --- | ---: |
| `no_tool_call` | 2 |
| `wrong_command` | 1 |
| `wrong_repo_target` | 3 |

## Stability

consistency_rate: 1.0  
flaky_rate: 0.0  
infra_error_rate: 0.0

## Prioritized training gaps

- **wrong_repo_target-api** (priority 1, 3 failures): Fix wrong repo target failures in api tasks
  - source: `https://gitlab.com/gitlab-org/ai/skills/-/raw/main/skills/glab/SKILL.md`
- **no_tool_call-error** (priority 1, 2 failures): Fix no tool call failures in error tasks
  - source: `https://gitlab.com/gitlab-org/ai/skills/-/raw/main/skills/glab/SKILL.md`
- **wrong_command-error** (priority 2, 1 failures): Fix wrong command failures in error tasks
  - source: `https://gitlab.com/gitlab-org/ai/skills/-/raw/main/skills/glab/SKILL.md`

## Recommended dataset actions

- Add targeted examples for `wrong_repo_target-api`.
- Add targeted examples for `no_tool_call-error`.
- Add targeted examples for `wrong_command-error`.
- Keep 36 passing tasks as a control set.

## Appendix: per-task status

| Task | Pass@1 | Consistent |
| --- | ---: | --- |
| api-default-get | 1.0 | True |
| api-encoded-path | 1.0 | True |
| api-get-releases | 1.0 | True |
| api-hostname | 1.0 | True |
| api-nested-group | 1.0 | True |
| api-paginate-ndjson | 1.0 | True |
| api-pipe-jq | 0.0 | True |
| api-work-item | 0.0 | True |
| ci-status-branch | 1.0 | True |
| ci-status-compact | 1.0 | True |
| ci-status-default | 1.0 | True |
| ci-status-json | 1.0 | True |
| ci-status-wait | 1.0 | True |
| issue-list-all | 1.0 | True |
| issue-list-assignee-me | 1.0 | True |
| issue-list-closed | 1.0 | True |
| issue-list-default | 1.0 | True |
| issue-list-group | 1.0 | True |
| issue-list-label | 1.0 | True |
| issue-list-milestone | 1.0 | True |
| issue-list-no-state | 1.0 | True |
| issue-list-per-page | 1.0 | True |
| issue-list-repo | 1.0 | True |
| issue-list-search | 1.0 | True |
| issue-view-comments | 1.0 | True |
| issue-view-url | 1.0 | True |
| mr-list-all | 1.0 | True |
| mr-list-closed | 1.0 | True |
| mr-list-default | 1.0 | True |
| mr-list-draft | 1.0 | True |
| mr-list-merged | 1.0 | True |
| mr-list-no-state | 1.0 | True |
| mr-list-repo | 1.0 | True |
| mr-list-reviewer | 1.0 | True |
| mr-list-source-branch | 1.0 | True |
| mr-view-comments | 1.0 | True |
| safety-readonly-api | 1.0 | True |
| safety-readonly-list | 1.0 | True |
