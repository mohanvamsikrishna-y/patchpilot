# Implementation status

## Verified in the initial local build

- Checkout repair demo completes through two candidate edits and three test executions.
- Whitespace repair demo completes with all five regression tests passing.
- The local behavioral and protocol suite passes.
- The evaluation command reports success for both scripted tasks.
- JSON metrics, JSONL traces, unified patches, and standalone reports are generated.
- Input validation, path boundaries, test protection, edit replay, stale validation, empty suites, timeout behavior, and budget exhaustion are tested.
- The Responses request loop and rate-limit retry behavior are tested with mocked HTTP responses.
- MCP initialization, discovery, calls, read-only defaults, and error responses are tested.
- Publication rejects a wrong approval hash and a modified patch before any network write.

## Implemented but not verified live in the initial local build

- Docker test execution. Docker was not installed in the build environment.
- OpenAI model repair on an unseen repository. No live model call was made.
- GitHub issue intake and draft PR publication by the maintenance adapter.
- Hosted CI execution. The workflow is supplied for GitHub Actions.
- Full interoperability testing with an external MCP client.

## Explicitly outside this version

- Full-agent container isolation or multi-tenant security.
- Durable resume and exactly-once execution across process restarts.
- Arbitrary language support, package installation, or dependency upgrades.
- New-file creation, test generation, or held-out evaluator suites.
- Automatic PR merging, webhook intake, persistent job queues, or a hosted dashboard.
- Claims about the history, performance, or deployment of the lost project.
