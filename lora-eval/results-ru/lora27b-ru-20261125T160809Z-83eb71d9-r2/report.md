# glab CLI evaluation report — lora27b-ru-20261125T160809Z-83eb71d9-r2

Created: 2026-11-25T16:08:09.257675+00:00  
Suite: lora27b-ru (r2)  
Model: glab27b (/workspace/adapter)  
vLLM: 0.33.0  
Sources: glab 1.100.0, skill 1.16.2, retrieved 2026-11-21T18:52:52Z

## Headline metrics

| Metric | Value |
| --- | ---: |
| `total_responses` | 114 |
| `model_responses` | 114 |
| `infra_errors` | 0 |
| `pass_rate` | 0.9561 |
| `valid_tool_call_rate` | 1.0 |
| `xml_parse_success_rate` | None |
| `normalized_command_match` | 0.9561 |
| `required_flags_present` | 1.0 |
| `forbidden_absent` | 1.0 |
| `avg_latency_ms` | 7809.9052 |
| `avg_reasoning_tokens` | 53.1754 |
| `avg_completion_tokens` | 92.0526 |

## Coverage by category

| Category | Responses | Pass rate | Valid tool call |
| --- | ---: | ---: | ---: |
| api | 21 | 0.9048 | 1.0 |
| ci | 15 | 1.0 | 1.0 |
| error | 9 | 0.7778 | 1.0 |
| issue | 36 | 0.9722 | 1.0 |
| mr | 27 | 1.0 | 1.0 |
| safety | 6 | 1.0 | 1.0 |

## Failures by error type

| Error type | Count |
| --- | ---: |
| `invalid_flag` | 1 |
| `wrong_command` | 2 |
| `wrong_repo_target` | 2 |

## Stability

consistency_rate: 0.9211  
flaky_rate: 0.0789  
infra_error_rate: 0.0

## Prioritized training gaps

- **flaky-needs-review** (priority 3, 5 failures): Manually review unstable tasks before adding them to training data
  - source: `https://gitlab.com/gitlab-org/ai/skills/-/raw/main/skills/glab/SKILL.md`
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/issue/list.md`

## Recommended dataset actions

- Add targeted examples for `flaky-needs-review`.
- Keep 35 passing tasks as a control set.
- Manually review 3 flaky tasks before training.

## Appendix: per-task status

| Task | Pass@1 | Consistent |
| --- | ---: | --- |
| api-default-get | 1.0 | True |
| api-encoded-path | 1.0 | True |
| api-get-releases | 1.0 | True |
| api-hostname | 1.0 | True |
| api-nested-group | 1.0 | True |
| api-paginate-ndjson | 1.0 | True |
| api-pipe-jq | 0.3333 | False |
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
| issue-list-repo | 0.6667 | False |
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
