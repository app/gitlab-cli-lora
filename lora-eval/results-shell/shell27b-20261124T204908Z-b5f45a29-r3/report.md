# glab CLI evaluation report — shell27b-20261124T204908Z-b5f45a29-r3

Created: 2026-11-24T20:49:08.569666+00:00  
Suite: shell27b (r3)  
Model: glab27b (/workspace/adapter)  
vLLM: 0.33.0  
Sources: glab 1.100.0, skill 1.16.2, retrieved 2026-11-21T18:52:52Z

## Headline metrics

| Metric | Value |
| --- | ---: |
| `total_responses` | 114 |
| `model_responses` | 114 |
| `infra_errors` | 0 |
| `pass_rate` | 0.9386 |
| `valid_tool_call_rate` | 0.9912 |
| `xml_parse_success_rate` | None |
| `normalized_command_match` | 0.9386 |
| `required_flags_present` | 0.9825 |
| `forbidden_absent` | 1.0 |
| `avg_latency_ms` | 9458.4418 |
| `avg_reasoning_tokens` | 62.1667 |
| `avg_completion_tokens` | 97.807 |

## Coverage by category

| Category | Responses | Pass rate | Valid tool call |
| --- | ---: | ---: | ---: |
| api | 21 | 0.8571 | 1.0 |
| ci | 15 | 0.9333 | 0.9333 |
| error | 9 | 0.7778 | 1.0 |
| issue | 36 | 0.9722 | 1.0 |
| mr | 27 | 1.0 | 1.0 |
| safety | 6 | 1.0 | 1.0 |

## Failures by error type

| Error type | Count |
| --- | ---: |
| `invalid_json_args` | 1 |
| `wrong_command` | 2 |
| `wrong_repo_target` | 4 |

## Stability

consistency_rate: 0.9211  
flaky_rate: 0.0789  
infra_error_rate: 0.0

## Prioritized training gaps

- **wrong_repo_target-api** (priority 1, 3 failures): Fix wrong repo target failures in api tasks
  - source: `https://gitlab.com/gitlab-org/ai/skills/-/raw/main/skills/glab/SKILL.md`
- **flaky-needs-review** (priority 3, 4 failures): Manually review unstable tasks before adding them to training data
  - source: `https://gitlab.com/gitlab-org/ai/skills/-/raw/main/skills/glab/SKILL.md`
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/ci/status.md`

## Recommended dataset actions

- Add targeted examples for `wrong_repo_target-api`.
- Add targeted examples for `flaky-needs-review`.
- Keep 34 passing tasks as a control set.
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
| api-work-item | 0.0 | True |
| ci-status-branch | 1.0 | True |
| ci-status-compact | 1.0 | True |
| ci-status-default | 1.0 | True |
| ci-status-json | 1.0 | True |
| ci-status-wait | 0.6667 | False |
| issue-list-all | 1.0 | True |
| issue-list-assignee-me | 1.0 | True |
| issue-list-closed | 1.0 | True |
| issue-list-default | 1.0 | True |
| issue-list-group | 1.0 | True |
| issue-list-label | 1.0 | True |
| issue-list-milestone | 1.0 | True |
| issue-list-no-state | 1.0 | True |
| issue-list-per-page | 0.6667 | False |
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
