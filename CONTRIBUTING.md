# Working on PatchPilot

Read the [codebase walkthrough](docs/code-guide.md) before changing the controller or tools. Keep model proposal logic in providers and execution policy in the tool layer.

## Local setup

The source checkout runs with Python 3.10 or newer and Git. Runtime dependencies are standard-library only.

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e '.[dev]'
```

The optional development extra installs the pinned formatter. It is not needed to run a demo.

## Check a change

```sh
make format
make format-check
make check
```

`make check` runs the behavioral tests, scripted golden tasks, and syntax checks. It does not invoke a paid model. Live runs are a separate manual check.

```sh
python3 -m patchpilot demo --provider codex --open
```

## Keep the code readable

- Give each module one clear responsibility.
- Document functions with their purpose, inputs or outputs when unclear, and important side effects.
- Use inline comments to explain a decision or invariant that the code alone does not make obvious.
- Keep the distinction between tool execution and test success explicit.
- Update the code guide and status notes when behavior or verification changes.
- Add a behavioral test for a changed policy boundary or failure mode.

Comments should match the implementation. Avoid claims of hard isolation, durable replay, or spending guarantees that the current code cannot enforce.

## Fixtures and saved evidence

The bugs under `examples/` are intentional. The scripted actions use exact string matches, so changing fixture formatting can invalidate those actions. Keep the fixture source, actions, and regression tests consistent when changing a task.

The checked-in reports under `docs/` are historical evidence. Do not rewrite their outcomes to match later behavior. Generate a new run when collecting new evidence, and remove personal paths before sharing it.

Personal preparation notes, credentials, and generated `runs/` folders stay out of Git. Review the staged diff before publishing.
