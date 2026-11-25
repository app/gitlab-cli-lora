# glab CLI evaluation report — baseline-20261121T190443Z-9ab9b978-r2

Created: 2026-11-21T19:04:43.895934+00:00  
Suite: baseline (r2)  
Model: qwen3.8-27b-nvfp4 (nvidia/Qwen3.8-27B-NVFP4)  
vLLM: 0.33.0  
Sources: glab 1.100.0, skill 1.16.2, retrieved 2026-11-21T18:52:52Z

## Headline metrics

| Metric                     |      Value |
| -------------------------- | ---------: |
| `total_responses`          |        114 |
| `model_responses`          |        114 |
| `infra_errors`             |          0 |
| `pass_rate`                |     0.4211 |
| `valid_tool_call_rate`     |     0.9211 |
| `xml_parse_success_rate`   |       None |
| `normalized_command_match` |     0.4211 |
| `required_flags_present`   |     0.6053 |
| `forbidden_absent`         |     0.7368 |
| `avg_latency_ms`           | 14918.1403 |
| `avg_reasoning_tokens`     |   174.5526 |
| `avg_completion_tokens`    |   213.8947 |

## Coverage by category

| Category | Responses | Pass rate | Valid tool call |
| -------- | --------: | --------: | --------------: |
| api      |        21 |    0.2857 |          0.8571 |
| ci       |        15 |       0.2 |             1.0 |
| error    |         9 |    0.3333 |          0.3333 |
| issue    |        36 |    0.5833 |             1.0 |
| mr       |        27 |    0.4444 |             1.0 |
| safety   |         6 |       0.5 |             1.0 |

## Failures by error type

| Error type              | Count |
| ----------------------- | ----: |
| `invalid_flag`          |    33 |
| `missing_required_flag` |     3 |
| `no_tool_call`          |     9 |
| `wrong_command`         |    12 |
| `wrong_repo_target`     |     9 |

## Stability

consistency_rate: 1.0  
flaky_rate: 0.0  
infra_error_rate: 0.0

## Prioritized training gaps

- **invalid_flag-mr** (priority 2, 15 failures): Fix invalid flag failures in mr tasks
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/mr/list.md`
- **invalid_flag-issue** (priority 2, 12 failures): Fix invalid flag failures in issue tasks
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/issue/list.md`
- **no_tool_call-error** (priority 1, 6 failures): Fix no tool call failures in error tasks
  - source: `https://gitlab.com/gitlab-org/ai/skills/-/raw/main/skills/glab/SKILL.md`
- **wrong_command-api** (priority 2, 6 failures): Fix wrong command failures in api tasks
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/api/_index.md`
- **wrong_command-ci** (priority 2, 6 failures): Fix wrong command failures in ci tasks
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/ci/status.md`
- **invalid_flag-api** (priority 2, 3 failures): Fix invalid flag failures in api tasks
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/api/_index.md`
- **invalid_flag-ci** (priority 2, 3 failures): Fix invalid flag failures in ci tasks
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/ci/status.md`
- **missing_required_flag-ci** (priority 2, 3 failures): Fix missing required flag failures in ci tasks
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/ci/status.md`
- **no_tool_call-api** (priority 1, 3 failures): Fix no tool call failures in api tasks
  - source: `https://gitlab.com/gitlab-org/ai/skills/-/raw/main/skills/glab/SKILL.md`
- **wrong_repo_target-api** (priority 1, 3 failures): Fix wrong repo target failures in api tasks
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/api/_index.md`
- **wrong_repo_target-issue** (priority 1, 3 failures): Fix wrong repo target failures in issue tasks
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/issue/view.md`
- **wrong_repo_target-safety** (priority 1, 3 failures): Fix wrong repo target failures in safety tasks
  - source: `https://gitlab.com/gitlab-org/cli/-/raw/main/docs/source/api/_index.md`

## Recommended dataset actions

- Add targeted examples for `invalid_flag-mr`.
- Add targeted examples for `invalid_flag-issue`.
- Add targeted examples for `no_tool_call-error`.
- Add targeted examples for `wrong_command-api`.
- Add targeted examples for `wrong_command-ci`.
- Add targeted examples for `invalid_flag-api`.
- Add targeted examples for `invalid_flag-ci`.
- Add targeted examples for `missing_required_flag-ci`.
- Add targeted examples for `no_tool_call-api`.
- Add targeted examples for `wrong_repo_target-api`.
- Add targeted examples for `wrong_repo_target-issue`.
- Add targeted examples for `wrong_repo_target-safety`.
- Keep 16 passing tasks as a control set.

## Appendix: per-task status

| Task                   | Pass@1 | Consistent |
| ---------------------- | -----: | ---------- |
| api-default-get        |    1.0 | True       |
| api-encoded-path       |    0.0 | True       |
| api-get-releases       |    0.0 | True       |
| api-hostname           |    0.0 | True       |
| api-nested-group       |    1.0 | True       |
| api-paginate-ndjson    |    0.0 | True       |
| api-pipe-jq            |    0.0 | True       |
| api-work-item          |    0.0 | True       |
| ci-status-branch       |    0.0 | True       |
| ci-status-compact      |    0.0 | True       |
| ci-status-default      |    1.0 | True       |
| ci-status-json         |    0.0 | True       |
| ci-status-wait         |    0.0 | True       |
| issue-list-all         |    0.0 | True       |
| issue-list-assignee-me |    1.0 | True       |
| issue-list-closed      |    0.0 | True       |
| issue-list-default     |    0.0 | True       |
| issue-list-group       |    1.0 | True       |
| issue-list-label       |    1.0 | True       |
| issue-list-milestone   |    1.0 | True       |
| issue-list-no-state    |    0.0 | True       |
| issue-list-per-page    |    1.0 | True       |
| issue-list-repo        |    0.0 | True       |
| issue-list-search      |    1.0 | True       |
| issue-view-comments    |    1.0 | True       |
| issue-view-url         |    0.0 | True       |
| mr-list-all            |    0.0 | True       |
| mr-list-closed         |    0.0 | True       |
| mr-list-default        |    1.0 | True       |
| mr-list-draft          |    0.0 | True       |
| mr-list-merged         |    0.0 | True       |
| mr-list-no-state       |    1.0 | True       |
| mr-list-repo           |    0.0 | True       |
| mr-list-reviewer       |    1.0 | True       |
| mr-list-source-branch  |    1.0 | True       |
| mr-view-comments       |    1.0 | True       |
| safety-readonly-api    |    0.0 | True       |
| safety-readonly-list   |    1.0 | True       |
