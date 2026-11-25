# Training data

SFT datasets for the glab adapter. Everything under `tasks/` and `url/` is
generated; do not edit the generated files by hand. Specs live next to their
family, and the frozen serving contract lives under `contracts/`.

## Layout

```text
train/data/
  contracts/opencode/            frozen OpenCode serving contract (system prompt,
                                 shell tool, captured request); see its README
  tasks/                         family 1: the 38 frozen evaluation tasks
    spec/paraphrases.<lang>.jsonl
    glab/<lang>/{sft.jsonl,dataset_manifest.json}
    shell/<lang>/{sft.jsonl,dataset_manifest.json}
  url/                           family 2: URL-entity resolution
    spec/slots.jsonl             slots: group, project, iid, URL form, split
    spec/phrasings.json          phrasings per language and kind
    glab/<lang>/{sft.jsonl,dataset_manifest.json,heldout.<lang>.jsonl}
    shell/<lang>/{sft.jsonl,dataset_manifest.json,heldout.<lang>.jsonl}
  ext/                           family 3: lean command surface (shell only)
    spec/tasks.ext.jsonl         prompt sets, canonical command, split
    shell/<lang>/{sft.jsonl,dataset_manifest.json,heldout.<lang>.jsonl}
```

`glab` is the synthetic benchmark contract (`run_glab_command`, used by the
frozen 38-task suites); `shell` is the production OpenCode contract. The
prompts and target commands are identical — only the rendered system prompt
and tool schema differ.

## Sizes

| Dataset               |      Rows |
| --------------------- | --------: |
| `tasks/glab/{en,ru}`  | 180 + 180 |
| `tasks/shell/{en,ru}` | 180 + 180 |
| `url/glab/{en,ru}`    |   66 + 66 |
| `url/shell/{en,ru}`   |   66 + 66 |
| total                 |       984 |

`url/*/heldout.<lang>.jsonl` and `ext/shell/*/heldout.<lang>.jsonl` rows are
never trained; they hold the held-out project/phrasing (url) and held-out tasks
(ext) used to check generalization. The ext family is shell-shape only: the
`glab` benchmark contract stays frozen for the 38 tasks and is not extended.

## Rules enforced by `train/validate_dataset.py`

- generated rows re-render byte-identically from the frozen template;
- targets are read-only `glab` invocations and match the spec exactly;
- no prompt equals an evaluation prompt, and held-out prompts never leak into
  training;
- the URL family maps any GitLab issue/work-item URL to
  `glab issue view <url>` and REST phrasing to
  `glab api "projects/<group>%2F<project>/issues/N"`; the `work_items` API
  endpoint and any GraphQL target are rejected.

## Regenerate

```sh
uv run --project train python train/build_dataset.py --lang en --shape glab
uv run --project train python train/build_dataset.py --lang en --shape shell
uv run --project train python train/build_dataset.py --family url --lang en --shape shell
uv run --project train python train/build_dataset.py --family ext --lang en --shape shell
uv run --project train python train/validate_dataset.py --lang all
```
