# Training brief — baseline-ru-20261124T185205Z-044ff59a-r2

Overall pass rate: 0.3684

## Priority slices

### invalid_flag-issue (priority 2)

Fix invalid flag failures in issue tasks

- `glab issue list --all` ← Выведи задачи проекта целиком, включая закрытые.
- `glab issue list --closed` ← Мне нужен список только закрытых задач этого проекта.
- `glab issue list` ← Покажи список открытых задач в текущем проекте.
- `glab issue list --group org/subgroup` ← Покажи открытые задачи группы org/subgroup, а не текущего проекта.
- `glab issue list --repo group/project` ← Покажи открытые задачи репозитория group/project.
- `glab issue list --search timeout` ← Найди задачи, в тексте которых встречается timeout.

### invalid_flag-mr (priority 2)

Fix invalid flag failures in mr tasks

- `glab mr list --all` ← Выведи все merge request, включая закрытые и смерженные.
- `glab mr list --closed` ← Мне нужны только закрытые merge request.
- `glab mr list --merged` ← Выведи список смерженных merge request.
- `glab mr list --repo group/project` ← Покажи открытые merge request репозитория group/project.

### wrong_command-api (priority 2)

Fix wrong command failures in api tasks

- `glab api projects/:fullpath` ← Прочитай projects/:fullpath методом по умолчанию.
- `glab api projects/gitlab-com%2Fwww-gitlab-com/issues` ← Покажи задачи gitlab-com/www-gitlab-com, закодировав путь проекта.
- `glab api projects/:fullpath/releases` ← Покажи релизы текущего проекта через API.
- `glab api --hostname example.com user` ← Получи /user с инстанса example.com.

### no_tool_call-api (priority 1)

Fix no tool call failures in api tasks

- `glab api "groups/org%2Fsubgroup/epics"` ← Покажи эпики вложенной группы org/subgroup через API.
- `glab api issues --paginate --output ndjson` ← Выведи все задачи постранично в NDJSON.
- `glab api --method GET "projects/org%2Fproject/issues/539076"` ← Получи work item 539076 из org/project через issues, а не work_items.

### missing_required_flag-ci (priority 2)

Fix missing required flag failures in ci tasks

- `glab ci status --compact` ← Выведи статус пайплайна в компактном формате.
- `glab ci status --wait` ← Дождись завершения пайплайна и покажи результат без запросов.

### invalid_flag-error (priority 2)

Fix invalid flag failures in error tasks

- `glab issue list` ← Покажи открытые задачи. В подсказке был флаг --state opened, но нужна корректная команда glab.

### no_tool_call-ci (priority 1)

Fix no tool call failures in ci tasks

- `glab ci status --output json` ← Выведи статус пайплайна в JSON, без --live, --wait и --compact.

### no_tool_call-error (priority 1)

Fix no tool call failures in error tasks

- `glab api --method GET "search?scope=issues&search=<query>" | jq '.[] | {iid, title}'` ← Найди задачи через scope=issues и извлеки заголовки через jq, без --jq.

### wrong_command-safety (priority 2)

Fix wrong command failures in safety tasks

- `glab api projects/:fullpath/issues` ← Прочитай задачи проекта через API без POST, PUT и DELETE.

### wrong_repo_target-issue (priority 1)

Fix wrong repo target failures in issue tasks

- `glab issue view https://gitlab.com/NAMESPACE/REPO/-/issues/123` ← Открой задачу по ссылке https://gitlab.com/NAMESPACE/REPO/-/issues/123 и покажи её.

## Constraints

- Native Qwen3.8 XML tool-call targets (`qwen3_5_native_xml`).
- `reasoning_effort=low`.
- No glab command is ever executed.

Control tasks: 14; stable failures: 24; flaky: 0.
