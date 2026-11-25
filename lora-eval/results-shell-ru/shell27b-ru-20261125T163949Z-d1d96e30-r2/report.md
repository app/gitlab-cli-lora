# glab CLI evaluation report — shell27b-ru-20261125T163949Z-d1d96e30-r2

Created: 2026-11-25T16:39:49.861043+00:00  
Suite: shell27b-ru (r2)  
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
| `valid_tool_call_rate` | 0.9912 |
| `xml_parse_success_rate` | None |
| `normalized_command_match` | 0.9474 |
| `required_flags_present` | 0.9912 |
| `forbidden_absent` | 1.0 |
| `avg_latency_ms` | 8987.9558 |
| `avg_reasoning_tokens` | 55.5789 |
| `avg_completion_tokens` | 92.2105 |

## Coverage by category

| Category | Responses | Pass rate | Valid tool call |
| --- | ---: | ---: | ---: |
| api | 21 | 0.8571 | 0.9524 |
| ci | 15 | 1.0 | 1.0 |
| error | 9 | 0.6667 | 1.0 |
| issue | 36 | 1.0 | 1.0 |
| mr | 27 | 1.0 | 1.0 |
| safety | 6 | 1.0 | 1.0 |

## Failures by error type

| Error type | Count |
| --- | ---: |
| `no_tool_call` | 1 |
| `wrong_command` | 3 |
| `wrong_repo_target` | 2 |

## Stability

consistency_rate: 0.9474  
flaky_rate: 0.0526  
infra_error_rate: 0.0

## Prioritized training gaps

- **wrong_command-error** (priority 2, 3 failures): Fix wrong command failures in error tasks
  - source: `https://gitlab.com/gitlab-org/ai/skills/-/raw/main/skills/glab/SKILL.md`
- **flaky-needs-review** (priority 3, 3 failures): Manually review unstable tasks before adding them to training data
  - source: `https://gitlab.com/gitlab-org/ai/skills/-/raw/main/skills/glab/SKILL.md`
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/api/_index.md`

## Recommended dataset actions

- Add targeted examples for `wrong_command-error`.
- Add targeted examples for `flaky-needs-review`.
- Keep 35 passing tasks as a control set.
- Manually review 2 flaky tasks before training.

## Appendix: per-task status

| Task | Pass@1 | Consistent |
| --- | ---: | --- |
| api-default-get | 1.0 | True |
| api-encoded-path | 1.0 | True |
| api-get-releases | 0.6667 | False |
| api-hostname | 1.0 | True |
| api-nested-group | 1.0 | True |
| api-paginate-ndjson | 1.0 | True |
| api-pipe-jq | 0.0 | True |
| api-work-item | 0.3333 | False |
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
