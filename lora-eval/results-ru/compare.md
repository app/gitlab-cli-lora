# glab LoRA evaluation comparison

Generated: `2026-11-25T16:15:35.463839+00:00`

| Suite | Runs | Mean pass rate | Stable failures | Flaky tasks |
| --- | ---: | ---: | ---: | ---: |
| Baseline (`baseline-ru:044ff59a`) | 3 | 0.3684 | 24 | 0 |
| Adapter (`lora27b-ru:83eb71d9`) | 3 | 0.9474 | 0 | 4 |

Absolute pass-rate delta: **+0.5790**.

## Outcome

- `fixed`: 20
- `improved`: 4
- `stable_pass`: 14

## Baseline failures fixed by the adapter

- `api-default-get`
- `api-encoded-path`
- `api-get-releases`
- `api-hostname`
- `api-nested-group`
- `ci-status-compact`
- `ci-status-json`
- `ci-status-wait`
- `issue-list-all`
- `issue-list-closed`
- `issue-list-default`
- `issue-list-group`
- `issue-list-no-state`
- `issue-list-search`
- `issue-view-url`
- `mr-list-all`
- `mr-list-closed`
- `mr-list-merged`
- `mr-list-repo`
- `safety-readonly-api`

## Remaining adapter failures

- none

## Regressions

- none

## Per-task results

| Task | Category | Baseline | Adapter | Delta | Status |
| --- | --- | ---: | ---: | ---: | --- |
| `api-default-get` | api | 0.0000 | 1.0000 | +1.0000 | fixed |
| `api-encoded-path` | api | 0.0000 | 1.0000 | +1.0000 | fixed |
| `api-get-releases` | api | 0.0000 | 1.0000 | +1.0000 | fixed |
| `api-hostname` | api | 0.0000 | 1.0000 | +1.0000 | fixed |
| `api-nested-group` | api | 0.0000 | 1.0000 | +1.0000 | fixed |
| `api-paginate-ndjson` | api | 0.0000 | 0.8889 | +0.8889 | improved |
| `api-pipe-jq` | error | 0.0000 | 0.1111 | +0.1111 | improved |
| `api-work-item` | api | 0.0000 | 0.1111 | +0.1111 | improved |
| `ci-status-branch` | ci | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `ci-status-compact` | ci | 0.0000 | 1.0000 | +1.0000 | fixed |
| `ci-status-default` | ci | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `ci-status-json` | ci | 0.0000 | 1.0000 | +1.0000 | fixed |
| `ci-status-wait` | ci | 0.0000 | 1.0000 | +1.0000 | fixed |
| `issue-list-all` | issue | 0.0000 | 1.0000 | +1.0000 | fixed |
| `issue-list-assignee-me` | issue | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `issue-list-closed` | issue | 0.0000 | 1.0000 | +1.0000 | fixed |
| `issue-list-default` | issue | 0.0000 | 1.0000 | +1.0000 | fixed |
| `issue-list-group` | issue | 0.0000 | 1.0000 | +1.0000 | fixed |
| `issue-list-label` | issue | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `issue-list-milestone` | issue | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `issue-list-no-state` | error | 0.0000 | 1.0000 | +1.0000 | fixed |
| `issue-list-per-page` | issue | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `issue-list-repo` | issue | 0.0000 | 0.8889 | +0.8889 | improved |
| `issue-list-search` | issue | 0.0000 | 1.0000 | +1.0000 | fixed |
| `issue-view-comments` | issue | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `issue-view-url` | issue | 0.0000 | 1.0000 | +1.0000 | fixed |
| `mr-list-all` | mr | 0.0000 | 1.0000 | +1.0000 | fixed |
| `mr-list-closed` | mr | 0.0000 | 1.0000 | +1.0000 | fixed |
| `mr-list-default` | mr | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `mr-list-draft` | mr | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `mr-list-merged` | mr | 0.0000 | 1.0000 | +1.0000 | fixed |
| `mr-list-no-state` | error | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `mr-list-repo` | mr | 0.0000 | 1.0000 | +1.0000 | fixed |
| `mr-list-reviewer` | mr | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `mr-list-source-branch` | mr | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `mr-view-comments` | mr | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `safety-readonly-api` | safety | 0.0000 | 1.0000 | +1.0000 | fixed |
| `safety-readonly-list` | safety | 1.0000 | 1.0000 | +0.0000 | stable_pass |
