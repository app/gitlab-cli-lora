# glab CLI evaluation report — lora27b-20261122T075850Z-5296702b-r3

Created: 2026-11-22T07:58:50.239889+00:00  
Suite: lora27b (r3)  
Model: glab27b (/workspace/adapter)  
vLLM: 0.33.0  
Sources: glab 1.100.0, skill 1.16.2, retrieved 2026-11-21T18:52:52Z

## Headline metrics

| Metric | Value |
| --- | ---: |
| `total_responses` | 114 |
| `model_responses` | 114 |
| `infra_errors` | 0 |
| `pass_rate` | 0.8509 |
| `valid_tool_call_rate` | 1.0 |
| `xml_parse_success_rate` | None |
| `normalized_command_match` | 0.8509 |
| `required_flags_present` | 0.9386 |
| `forbidden_absent` | 0.9737 |
| `avg_latency_ms` | 11517.1402 |
| `avg_reasoning_tokens` | 98.4561 |
| `avg_completion_tokens` | 137.4561 |

## Coverage by category

| Category | Responses | Pass rate | Valid tool call |
| --- | ---: | ---: | ---: |
| api | 21 | 0.6667 | 1.0 |
| ci | 15 | 1.0 | 1.0 |
| error | 9 | 0.3333 | 1.0 |
| issue | 36 | 0.8889 | 1.0 |
| mr | 27 | 1.0 | 1.0 |
| safety | 6 | 1.0 | 1.0 |

## Failures by error type

| Error type | Count |
| --- | ---: |
| `invalid_flag` | 3 |
| `missing_required_flag` | 1 |
| `wrong_command` | 5 |
| `wrong_repo_target` | 8 |

## Stability

consistency_rate: 0.8947  
flaky_rate: 0.1053  
infra_error_rate: 0.0

## Prioritized training gaps

- **invalid_flag-error** (priority 2, 3 failures): Fix invalid flag failures in error tasks
  - source: `https://gitlab.com/gitlab-org/ai/skills/-/raw/main/skills/glab/SKILL.md`
- **wrong_command-error** (priority 2, 3 failures): Fix wrong command failures in error tasks
  - source: `https://gitlab.com/gitlab-org/ai/skills/-/raw/main/skills/glab/SKILL.md`
- **wrong_repo_target-api** (priority 1, 3 failures): Fix wrong repo target failures in api tasks
  - source: `https://gitlab.com/gitlab-org/ai/skills/-/raw/main/skills/glab/SKILL.md`
- **wrong_repo_target-issue** (priority 1, 3 failures): Fix wrong repo target failures in issue tasks
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/issue/view.md`
- **flaky-needs-review** (priority 3, 5 failures): Manually review unstable tasks before adding them to training data
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/api/_index.md`
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/issue/view.md`

## Recommended dataset actions

- Add targeted examples for `invalid_flag-error`.
- Add targeted examples for `wrong_command-error`.
- Add targeted examples for `wrong_repo_target-api`.
- Add targeted examples for `wrong_repo_target-issue`.
- Add targeted examples for `flaky-needs-review`.
- Keep 30 passing tasks as a control set.
- Manually review 4 flaky tasks before training.

## Appendix: per-task status

| Task | Pass@1 | Consistent |
| --- | ---: | --- |
| api-default-get | 0.6667 | False |
| api-encoded-path | 1.0 | True |
| api-get-releases | 0.6667 | False |
| api-hostname | 1.0 | True |
| api-nested-group | 1.0 | True |
| api-paginate-ndjson | 0.3333 | False |
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
| issue-list-no-state | 0.0 | True |
| issue-list-per-page | 1.0 | True |
| issue-list-repo | 1.0 | True |
| issue-list-search | 1.0 | True |
| issue-view-comments | 0.6667 | False |
| issue-view-url | 0.0 | True |
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
