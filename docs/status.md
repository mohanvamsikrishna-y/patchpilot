# Implementation status

## Verified

- Checkout repair demo completes through two candidate edits and three test executions.
- Whitespace repair demo completes with all five regression tests passing.
- The local behavioral and protocol suite passes.
- The evaluation command reports success for both scripted tasks.
- JSON metrics, JSONL traces, unified patches, and standalone reports are generated.
- Input validation, path boundaries, test protection, edit replay, stale validation, empty suites, timeout behavior, and budget exhaustion are tested.
- The Responses request loop and rate-limit retry behavior are tested with mocked HTTP responses.
- MCP initialization, discovery, calls, read-only defaults, and error responses are tested.
- Publication rejects a wrong approval hash and a modified patch before any network write.

The [first hosted CI run](https://github.com/mohanvamsikrishna-y/patchpilot/actions/runs/34508607637) passed on September 10, 2026, including Python 3.10 and 3.12 regression jobs and both golden tasks in Docker.

## Implemented but not verified live

- Direct OpenAI Responses API repair. The separate Codex CLI provider has been verified live on the seeded tasks described below.
- GitHub issue intake and draft PR publication by the maintenance adapter.
- Full interoperability testing with an external MCP client.

## Explicitly outside this version

- Full-agent container isolation or multi-tenant security.
- Durable resume and exactly-once execution across process restarts.
- Arbitrary language support, package installation, or dependency upgrades.
- New-file creation, test generation, or held-out evaluator suites.
- Automatic PR merging, webhook intake, persistent job queues, or a hosted dashboard.
- Claims about the history, performance, or deployment of the lost project.

## Live demo upgrade verified October 17, 2026

- Live Codex repair of the checkout task, from 1 of 5 to 5 of 5 passing tests.
- Live Codex repair of the slug task, from 1 of 5 to 5 of 5 passing tests.
- Both live runs generated their own edits from issue text and inspected files, without scripted action files.
- The checkout patch was applied through the local approval workflow and all five tests passed in that original demo checkout.
- The behavioral suite now contains 29 passing tests, including a mocked two-attempt live-provider repair, CLI response parsing, application approval, stale target rejection, setup failures, and stdin handling.
- Terminal progress, environment checks, persistent demo checkouts, latest-run lookup, downloadable report artifacts, and explicit unavailable-cost reporting are implemented.

Sanitized live evidence is stored under `docs/live-runs/`. These two seeded tasks do not establish general autonomous repair accuracy. The live tests used the local test runner; Docker results are tracked separately through CI.
