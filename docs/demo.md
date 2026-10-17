# Five-minute live demo

## Prepare before the call

Open a terminal in the PatchPilot repository. Run the readiness check.

```sh
python3 -m patchpilot doctor
```

Python and Git are required. For live AI repair, Codex sign-in must show ready. GitHub and Docker are optional for the bundled local demo. If needed, sign in with `codex login` before the interview. Do not display authentication files or API keys.

## Show a real model repair

```sh
python3 -m patchpilot demo --provider codex --open
```

Explain that the checkout function currently drops cents. The controller runs the original tests, reads source and tests through its tools, and sends those observations to Codex. Codex returns a structured proposal. PatchPilot validates the tool arguments, applies the edit, and runs tests again.

The model may solve the task on its first attempt. Do not imply it made multiple attempts when it did not. The saved verified checkout run needed one proposal. If a candidate fails, the adapter refreshes source and passes failure evidence into another proposal, up to its limits.

In the report, show the failing baseline, passing final suite, actual diff, and token counts. Cost is not reported by the Codex CLI, so the report does not invent a dollar figure.

## Show the human review gate

```sh
python3 -m patchpilot review --run latest
```

Explain that the original checkout has not changed. The review prints a target path and approval hash. After reading the patch, substitute those values below.

```sh
python3 -m patchpilot apply --run latest \
  --target /target/from/review --approve HASH_FROM_REVIEW
```

The change is applied as an uncommitted diff. It is not automatically published or merged. Open the target repository to show `git diff`. The application command refuses a dirty target, a changed patch, a changed base commit, or a wrong approval hash.

## Show a different task

```sh
python3 -m patchpilot demo --provider codex --task slug --open
```

This repairs repeated whitespace, tabs, and newlines in a slug utility. The live model reads the task and current files. It does not read `actions.json`.

## If the network fails

```sh
python3 -m patchpilot demo --open
```

Say that this is the scripted fallback. It exercises the same policy checks, edit tools, tests, report generation, and review gate. Its two predetermined candidates demonstrate failure feedback and repair. Use the saved live reports as evidence of previously measured AI runs, not as a claim that the offline fallback is live AI.

## Explain the engineering

Show `tests/test_live_workflow.py` for the failed-candidate repair test and approval checks. Show `codex_provider.py` for proposal generation, `tools.py` for policy, and `agent.py` for controller-owned validation.

The practical scope is small Python repositories with a unittest suite in `tests/`. Docker mode isolates test subprocesses, not the entire agent. Passing tests do not prove correctness beyond the suite. GitHub publication is implemented separately but has not been verified live by this adapter.
