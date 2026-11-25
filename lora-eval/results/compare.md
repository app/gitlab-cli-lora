# glab LoRA evaluation comparison

Generated: `2026-11-25T16:02:06.481910+00:00`

| Suite | Runs | Mean pass rate | Stable failures | Flaky tasks |
| --- | ---: | ---: | ---: | ---: |
| Baseline (`baseline:9ab9b978`) | 3 | 0.4201 | 22 | 1 |
| Adapter (`lora27b:2b69aac2`) | 3 | 0.9474 | 2 | 0 |

Absolute pass-rate delta: **+0.5273**.

## Outcome

- `fixed`: 20
- `stabilized`: 1
- `stable_pass`: 15
- `still_failing`: 2

## Baseline failures fixed by the adapter

- `api-encoded-path`
- `api-get-releases`
- `api-hostname`
- `api-paginate-ndjson`
- `ci-status-branch`
- `ci-status-compact`
- `ci-status-json`
- `ci-status-wait`
- `issue-list-all`
- `issue-list-closed`
- `issue-list-default`
- `issue-list-no-state`
- `issue-list-repo`
- `issue-view-url`
- `mr-list-all`
- `mr-list-closed`
- `mr-list-draft`
- `mr-list-merged`
- `mr-list-repo`
- `safety-readonly-api`

## Remaining adapter failures

- `api-pipe-jq`
- `api-work-item`

## Regressions

- none

## Per-task results

| Task | Category | Baseline | Adapter | Delta | Status |
| --- | --- | ---: | ---: | ---: | --- |
| `api-default-get` | api | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `api-encoded-path` | api | 0.0000 | 1.0000 | +1.0000 | fixed |
| `api-get-releases` | api | 0.0000 | 1.0000 | +1.0000 | fixed |
| `api-hostname` | api | 0.0000 | 1.0000 | +1.0000 | fixed |
| `api-nested-group` | api | 0.7778 | 1.0000 | +0.2222 | stabilized |
| `api-paginate-ndjson` | api | 0.0000 | 1.0000 | +1.0000 | fixed |
| `api-pipe-jq` | error | 0.0000 | 0.0000 | +0.0000 | still_failing |
| `api-work-item` | api | 0.0000 | 0.0000 | +0.0000 | still_failing |
| `ci-status-branch` | ci | 0.0000 | 1.0000 | +1.0000 | fixed |
| `ci-status-compact` | ci | 0.0000 | 1.0000 | +1.0000 | fixed |
| `ci-status-default` | ci | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `ci-status-json` | ci | 0.0000 | 1.0000 | +1.0000 | fixed |
| `ci-status-wait` | ci | 0.0000 | 1.0000 | +1.0000 | fixed |
| `issue-list-all` | issue | 0.0000 | 1.0000 | +1.0000 | fixed |
| `issue-list-assignee-me` | issue | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `issue-list-closed` | issue | 0.0000 | 1.0000 | +1.0000 | fixed |
| `issue-list-default` | issue | 0.0000 | 1.0000 | +1.0000 | fixed |
| `issue-list-group` | issue | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `issue-list-label` | issue | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `issue-list-milestone` | issue | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `issue-list-no-state` | error | 0.0000 | 1.0000 | +1.0000 | fixed |
| `issue-list-per-page` | issue | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `issue-list-repo` | issue | 0.0000 | 1.0000 | +1.0000 | fixed |
| `issue-list-search` | issue | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `issue-view-comments` | issue | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `issue-view-url` | issue | 0.0000 | 1.0000 | +1.0000 | fixed |
| `mr-list-all` | mr | 0.0000 | 1.0000 | +1.0000 | fixed |
| `mr-list-closed` | mr | 0.0000 | 1.0000 | +1.0000 | fixed |
| `mr-list-default` | mr | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `mr-list-draft` | mr | 0.0000 | 1.0000 | +1.0000 | fixed |
| `mr-list-merged` | mr | 0.0000 | 1.0000 | +1.0000 | fixed |
| `mr-list-no-state` | error | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `mr-list-repo` | mr | 0.0000 | 1.0000 | +1.0000 | fixed |
| `mr-list-reviewer` | mr | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `mr-list-source-branch` | mr | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `mr-view-comments` | mr | 1.0000 | 1.0000 | +0.0000 | stable_pass |
| `safety-readonly-api` | safety | 0.0000 | 1.0000 | +1.0000 | fixed |
| `safety-readonly-list` | safety | 1.0000 | 1.0000 | +0.0000 | stable_pass |
