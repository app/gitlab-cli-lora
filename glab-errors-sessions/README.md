# glab error corpus from OpenCode sessions

Real `glab` usage collected from every OpenCode session on this container. The
corpus records where the model tried to run `glab` and glab returned an error,
together with the user prompt that triggered the attempt and, when one exists,
the later successful correction.

## Layout

| File            | Content                                                               |
| --------------- | --------------------------------------------------------------------- |
| `collect.py`    | read-only collector, talks to the OpenCode service via `opencode api` |
| `records.jsonl` | every `glab` invocation found, classified, including successes        |
| `turns.jsonl`   | one row per user turn that ran `glab`: prompt, model, ordered calls   |
| `errors.jsonl`  | curated pure glab errors only; the main corpus                        |
| `summary.json`  | counts by class, project, model, prompt, and recovery                 |
| `manifest.json` | scan metadata and SHA256 of the outputs                               |

## Rerun

```sh
python3 collect.py
```

The collector needs a running OpenCode service and the `opencode` CLI with an
authenticated default server. It paginates `/api/session` and
`/api/session/{id}/message`, so it sees every project, not only the current
directory.

## Classification

`records.jsonl` classes:

| Class          | Meaning                                                    |
| -------------- | ---------------------------------------------------------- |
| `ok`           | glab finished without an error signature                   |
| `cli_usage`    | unknown command or flag, invalid argument format           |
| `api_endpoint` | REST call returned 404, usually a guessed endpoint or path |
| `graphql`      | GraphQL error body (`"errors": [`)                         |
| `repo_context` | glab could not detect the repository                       |
| `pipeline_jq`  | the surrounding `jq` failed; not a glab error              |
| `env_auth`     | token scope or authentication failure (401/403)            |
| `env_fs`       | filesystem or command lookup failure                       |
| `network`      | TLS timeout, refused connection                            |
| `aborted`      | the user interrupted the tool call                         |
| `other_exit`   | non-zero exit without a known signature                    |

`errors.jsonl` keeps only `cli_usage`, `api_endpoint`, `graphql`, and
`repo_context`; the rest stay in `records.jsonl` for auditability.

Detection is shell-aware: heredoc bodies, quoted strings, paths, and commit
messages that merely mention `glab` are ignored.

## Fields in `errors.jsonl`

- `id` — `session:message:index`
- `dedup_key` — hash of the invocation and normalized error output, for
  deduplicating repeated experiments
- `session`, `project`, `directory`, `title`, `model` — where and by which model
- `prompt` — the user message that started the turn
- `command` — the full shell command the model ran
- `invocations` — the extracted `glab ...` segments from the command
- `failure`, `failure_tag`, `exit`, `output` — the error
- `recovery` — the first later `ok` glab call in the same turn, or `null`

## Notes

- No credentials are stored. `glab auth status` masks tokens, and the corpus was
  checked for `glpat-` strings.
- The corpus is a snapshot: rerunning adds new sessions and rewrites the files.
