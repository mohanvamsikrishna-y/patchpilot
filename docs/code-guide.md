# Codebase walkthrough

Start with the controller in `patchpilot/agent.py`. Its main rule is simple. A provider proposes an action, a tool checks and executes it, and the controller records the result. A successful model response alone never makes a patch ready for review.

Use this guide beside the [demo walkthrough](demo.md). The demo shows the behavior. This guide shows where that behavior comes from.

## Suggested reading order

| Order | File | Start here | What to explain |
| --- | --- | --- | --- |
| 1 | [cli.py](../patchpilot/cli.py) | `main`, then `demo` | How the command selects a task and provider |
| 2 | [agent.py](../patchpilot/agent.py) | `run` | How baseline tests, tool calls, and saved evidence fit together |
| 3 | [codex_provider.py](../patchpilot/codex_provider.py) | `next`, then `propose` | How source and failures become a model proposal |
| 4 | [tools.py](../patchpilot/tools.py) | `call`, `replace_text`, `run_tests`, `finish` | Where the execution and validation rules are enforced |
| 5 | [runtime.py](../patchpilot/runtime.py) | `snapshot`, `command`, `tree_hash` | How workspaces, timeouts, and validation fingerprints work |
| 6 | [review.py](../patchpilot/review.py) | `apply_plan`, `apply_patch` | How a reviewed patch reaches the original checkout |
| 7 | [report.py](../patchpilot/report.py) | `render` | How recorded evidence becomes the HTML report |
| 8 | [test_live_workflow.py](../tests/test_live_workflow.py) | `test_codex_uses_observed_failure_for_second_candidate` | How the repair loop is tested without network calls |

## Follow one checkout repair

### The command chooses the workflow

```sh
python3 -m patchpilot demo --provider codex --open
```

Python enters [__main__.py](../patchpilot/__main__.py), which calls `cli.main`. The CLI parses the options and calls `demo`. That function copies the bundled checkout source and tests into a retained demo repository. It reads the issue separately and creates a `CodexProvider`.

The copied repository excludes `actions.json`. That file supplies the scripted fallback only. A live model does not receive a predetermined answer from it.

### The controller establishes evidence

`agent.run` creates a second, disposable workspace from the clean source repository. This is where agent edits happen. It first calls `run_tests` to establish the baseline. Missing tests or a runner failure stop the run before a model request.

The original checkout and the agent workspace have different jobs. The original remains unchanged for review. The workspace contains the candidate patch and test evidence.

### The provider prepares a candidate

`CodexProvider.next` starts with a repository search and queues file reads. Each tool result returns to the provider on the next iteration. Once those reads finish, `propose` sends the issue, current file contents, and test observations to Codex.

The model returns a JSON object with a plan, summary, and exact text replacements. The provider turns that proposal into a queue of ordinary PatchPilot tool calls. It does not write files directly.

### The tools enforce the rules

`Toolset.call` validates the tool name, exact fields, and argument types. `replace_text` then checks that the path is permitted, the file was read, a plan exists, and the old text occurs exactly once. Tests and workflow files are protected from that edit tool.

Each successful edit clears `validated_tree`. This prevents a previously passing test result from approving later, untested edits.

### Tests decide the next step

`run_tests` records a hash of the workspace, runs the fixed unittest command, and extracts the test counts. Validation requires passing tests, at least one passing test case, no timeout, and an unchanged tree during execution.

If tests fail, `CodexProvider.next` queues fresh file reads and asks for another proposal using the failure evidence. If tests pass, it requests `finish`. The `finish` tool checks the current hash again and requires a nonempty diff.

### Review is a separate action

The controller saves the patch, trace, metrics, PR description, and report. Its successful state is `awaiting_review`.

`review.apply_plan` verifies that the target checkout is clean and still at the tested source commit. The approval hash includes the target path, commit, and patch hash. `apply_patch` recomputes that plan before writing. It leaves an uncommitted diff and does not push or merge.

## The small contracts between modules

| Contract | Shape or rule |
| --- | --- |
| Provider action | A dictionary containing `name` and `arguments` |
| Tool observation | A dictionary containing `ok`, plus result fields or an error |
| Test observation | `ok` describes tool execution; `success` describes validation |
| Trace event | Step, tool name, arguments, result, and elapsed time |
| Validated tree | A fingerprint of permitted file paths and contents |
| Approval plan | Target or repository details bound to the reviewed patch |

For example, a test tool can return `ok = true` and `success = false`. That means the tests executed correctly and found a failing candidate. It is useful repair feedback, not an infrastructure failure.

## Other modules

| File | Responsibility |
| --- | --- |
| [providers.py](../patchpilot/providers.py) | Budget accounting, scripted actions, and the direct OpenAI API provider |
| [mcp.py](../patchpilot/mcp.py) | A synchronous MCP stdio adapter over the shared tools |
| [github.py](../patchpilot/github.py) | GitHub issue intake and separately approved draft PR publication |
| [doctor.py](../patchpilot/doctor.py) | Setup checks that do not expose credentials or invoke a model |
| [pyproject.toml](../pyproject.toml) | Package metadata, console entry point, and optional development tools |
| [ci.yml](../.github/workflows/ci.yml) | Regression tests, formatting, golden tasks, and Docker evaluation |

## Tests to open during an interview

| Concern | Test to show |
| --- | --- |
| A failed candidate feeds a second proposal | `test_codex_uses_observed_failure_for_second_candidate` in [test_live_workflow.py](../tests/test_live_workflow.py) |
| Applying a reviewed patch really works | `test_approved_patch_applies_to_original_and_passes_tests` in [test_live_workflow.py](../tests/test_live_workflow.py) |
| Changes after review invalidate approval | `test_target_changes_invalidate_approval` in [test_live_workflow.py](../tests/test_live_workflow.py) |
| Changes after tests invalidate validation | `test_stale_validation_rejected` in [test_tools.py](../tests/test_tools.py) |
| Repeating an edit does not apply it twice | `test_replay_is_idempotent` in [test_tools.py](../tests/test_tools.py) |
| A missing suite cannot count as success | `test_missing_suite_stops_before_any_model_call` in [test_live_workflow.py](../tests/test_live_workflow.py) |
| MCP returns compatible tool results | `test_mcp_initialization_discovery_and_results` in [test_protocols.py](../tests/test_protocols.py) |

## Design limits worth understanding

The tools' path checks and read-before-edit rules are useful controls, not a hardened sandbox. Local tests execute repository code with the user's permissions. Docker isolates test subprocesses, not the entire controller.

Edit replay state is in memory. It is not durable exactly-once execution across restarts. Local artifact hashes detect accidental changes; they do not authenticate a malicious user who can rewrite those artifacts.

The two live seeded tasks show that the integrated workflow works. They do not establish broad repair accuracy. Read [implementation status](status.md) before describing which integrations have been verified.
