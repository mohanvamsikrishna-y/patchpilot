# GitHub issue-to-PR workflow

The verified example is [issue #1](https://github.com/mohanvamsikrishna-y/patchpilot/issues/1) and [draft PR #2](https://github.com/mohanvamsikrishna-y/patchpilot/pull/2). The PR's remote test job passes. The baseline and final test results are retained in [the run evidence](github-run/run.json).

## Run a new complete session

You need Python, Git, a signed-in Codex CLI, and GitHub CLI access to a repository you can write to. Use a fresh output folder for each session.

```sh
python3 -m patchpilot github-demo \
  --repo YOUR_ACCOUNT/YOUR_REPO --output runs/github-session --open
```

This creates a small task project on an isolated branch, publishes its issue, reads the actual issue from GitHub, runs live model repair, and prepares a draft PR publication plan. It prints the exact next command, including the reviewed destination and approval hash.

Inspect the diff, tests, and report. Then run that printed command to create a draft PR. The PR is not merged automatically. Its target is the task branch, so the destination repository's main branch stays intact during the task workflow.

The published task baseline intentionally fails its regression suite. After the patch is proposed, the PR workflow runs those same tests remotely.

## Run the stages separately

These commands expose each boundary for a code walkthrough. Substitute your repository, branch, issue URL, and paths.

```sh
python3 -m patchpilot prepare-demo \
  --task cart --output runs/github-task \
  --github-repo YOUR_ACCOUNT/YOUR_REPO \
  --branch patchpilot-demo/checkout --push --create-issue
```

`demo.json` records the source path, baseline commit, branch, and issue URL. The task checkout excludes scripted action files.

```sh
python3 -m patchpilot run --provider codex \
  --repo runs/github-task/source --github-issue ISSUE_URL \
  --runner local --trust-local-code --output runs/repairs --open
```

The live provider receives the issue, inspected source, and real test observations. Local test execution is appropriate for this bundled task code. Use the Docker runner for the test isolation supported by the project.

```sh
python3 -m patchpilot publish-plan \
  --run RUN_DIRECTORY --repo YOUR_ACCOUNT/YOUR_REPO \
  --base patchpilot-demo/checkout
```

Review the patch and generated PR description. Approve the same plan with the same target branch.

```sh
python3 -m patchpilot publish \
  --run RUN_DIRECTORY --repo YOUR_ACCOUNT/YOUR_REPO \
  --base patchpilot-demo/checkout --approve PLAN_APPROVAL_HASH
```

The PR description links the issue and records the plan, before/after test counts, provider, and patch hash. A saved receipt makes an exact repeat return the same PR URL.

## Files to show

| File | Role |
| --- | --- |
| `demo_workspace.py` | Task preparation and workflow composition |
| `agent.py` | Baseline, repair loop, validation, and evidence |
| `codex_provider.py` | Live model proposals |
| `github.py` | Issue intake, approval plan, and draft PR publication |
| `test_github_workflow.py` | Real local Git transport tests and publication retries |
| `docs/github-run/` | Sanitized evidence from the verified remote session |
