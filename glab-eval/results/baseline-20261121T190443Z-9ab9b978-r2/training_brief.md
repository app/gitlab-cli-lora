# Training brief — baseline-20261121T190443Z-9ab9b978-r2

Overall pass rate: 0.4211

## Priority slices

### invalid_flag-mr (priority 2)

Fix invalid flag failures in mr tasks

- `glab mr list --all` ← List all merge requests, including merged and closed ones.
- `glab mr list --closed` ← Show only closed merge requests.
- `glab mr list --draft` ← List draft merge requests in the current project.
- `glab mr list --merged` ← Show only merged merge requests.
- `glab mr list --repo group/project` ← List open merge requests in the project group/project.

### invalid_flag-issue (priority 2)

Fix invalid flag failures in issue tasks

- `glab issue list --all` ← List all issues, including closed ones.
- `glab issue list --closed` ← Show only closed issues in the current project.
- `glab issue list` ← List open issues in the current project.
- `glab issue list --repo group/project` ← List open issues in the project group/project.

### no_tool_call-error (priority 1)

Fix no tool call failures in error tasks

- `glab api --method GET "search?scope=issues&search=<query>" | jq '.[] | {iid, title}'` ← Search issues with scope=issues and filter their titles with jq, without using a --jq flag on glab api.
- `glab issue list` ← Show open issues. The user suggested --state opened; give the correct glab command instead.

### wrong_command-api (priority 2)

Fix wrong command failures in api tasks

- `glab api projects/gitlab-com%2Fwww-gitlab-com/issues` ← List issues for gitlab-com/www-gitlab-com using a URL-encoded project path.
- `glab api --hostname example.com user` ← Read the /user endpoint from a self-managed GitLab instance at example.com.

### wrong_command-ci (priority 2)

Fix wrong command failures in ci tasks

- `glab ci status --branch main` ← Check the CI/CD pipeline status for the main branch.
- `glab ci status --output json` ← Get the pipeline status as JSON; do not combine JSON output with live, wait, or compact flags.

### invalid_flag-api (priority 2)

Fix invalid flag failures in api tasks

- `glab api issues --paginate --output ndjson` ← Fetch all pages of issues as newline-delimited JSON.

### invalid_flag-ci (priority 2)

Fix invalid flag failures in ci tasks

- `glab ci status --wait` ← Wait until the pipeline finishes and return output without a prompt.

### missing_required_flag-ci (priority 2)

Fix missing required flag failures in ci tasks

- `glab ci status --compact` ← Show the pipeline status in a compact format.

### no_tool_call-api (priority 1)

Fix no tool call failures in api tasks

- `glab api --method GET "projects/org%2Fproject/issues/539076"` ← Read work item 539076 from org/project through the issues REST API, not the work_items endpoint.

### wrong_repo_target-api (priority 1)

Fix wrong repo target failures in api tasks

- `glab api projects/:fullpath/releases` ← List releases for the current project through the GitLab API.

### wrong_repo_target-issue (priority 1)

Fix wrong repo target failures in issue tasks

- `glab issue view https://gitlab.com/NAMESPACE/REPO/-/issues/123` ← Display the issue at https://gitlab.com/NAMESPACE/REPO/-/issues/123.

### wrong_repo_target-safety (priority 1)

Fix wrong repo target failures in safety tasks

- `glab api projects/:fullpath/issues` ← Read project issues through the API without sending POST, PUT, or DELETE requests.

## Constraints

- Native Qwen3.8 XML tool-call targets (`qwen3_5_native_xml`).
- `reasoning_effort=low`.
- No glab command is ever executed.

Control tasks: 16; stable failures: 22; flaky: 0.
