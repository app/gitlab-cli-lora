# glab CLI evaluation report — smoke-20261121T185601Z-9ab9b978-r1

Created: 2026-11-21T18:56:01.160108+00:00  
Suite: smoke (r1)  
Model: qwen3.8-27b-nvfp4 (nvidia/Qwen3.8-27B-NVFP4)  
vLLM: 0.33.0  
Sources: glab 1.100.0, skill 1.16.2, retrieved 2026-11-21T18:52:52Z

## Headline metrics

| Metric                     |   Value |
| -------------------------- | ------: |
| `total_responses`          |       2 |
| `model_responses`          |       2 |
| `infra_errors`             |       0 |
| `pass_rate`                |     0.0 |
| `valid_tool_call_rate`     |     1.0 |
| `xml_parse_success_rate`   |    None |
| `normalized_command_match` |     0.0 |
| `required_flags_present`   |     0.5 |
| `forbidden_absent`         |     0.0 |
| `avg_latency_ms`           | 2209.86 |
| `avg_reasoning_tokens`     |    43.0 |
| `avg_completion_tokens`    |    80.0 |

## Coverage by category

| Category | Responses | Pass rate | Valid tool call |
| -------- | --------: | --------: | --------------: |
| issue    |         2 |       0.0 |             1.0 |

## Failures by error type

| Error type     | Count |
| -------------- | ----: |
| `invalid_flag` |     2 |

## Stability

consistency_rate: 1.0  
flaky_rate: 0.0  
infra_error_rate: 0.0

## Prioritized training gaps

- **invalid_flag-issue** (priority 2, 2 failures): Fix invalid flag failures in issue tasks
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/issue/list.md`

## Recommended dataset actions

- Add targeted examples for `invalid_flag-issue`.
- Keep 0 passing tasks as a control set.

## Appendix: per-task status

| Task               | Pass@1 | Consistent |
| ------------------ | -----: | ---------- |
| issue-list-closed  |    0.0 | True       |
| issue-list-default |    0.0 | True       |
