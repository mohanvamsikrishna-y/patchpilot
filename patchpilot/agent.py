"""The controller owns validation and publication eligibility, never the model."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import uuid

from .providers import Budget, BudgetExceeded
from .report import render
from .runtime import git, snapshot
from .tools import Toolset


def run(
    source: Path,
    issue: str,
    provider,
    output: Path,
    runner="local",
    budget=None,
    on_event=None,
    test_timeout=30,
    issue_url=None,
) -> dict:
    """Execute one issue-to-patch run and return its saved result dictionary.

    The provider proposes actions; Toolset decides whether they are permitted.
    Source is copied into a disposable workspace, so agent edits never touch the
    original checkout. Every executed action is appended to trace.jsonl.

    on_event receives those same events for terminal progress. Failures and
    cancellation still produce review artifacts, but cannot approve a patch.
    """
    budget = budget or Budget()
    if not issue.strip():
        raise ValueError("Issue cannot be empty")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    folder = output.resolve() / run_id
    workspace = folder / "workspace"
    started = time.monotonic()
    tools = Toolset(workspace, runner, test_timeout)
    events = []
    status, error, failure_mode, base = "failed", None, None, ""
    previous = None
    patch = ""

    def record(name, arguments, result):
        """Persist one observation before notifying the optional progress display."""
        event = {
            "step": budget.steps,
            "tool": name,
            "arguments": arguments,
            "result": result,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        events.append(event)
        with (folder / "trace.jsonl").open("a") as stream:
            stream.write(json.dumps(event) + "\n")
        if on_event:
            on_event(event)

    # Phase 1 establishes an isolated baseline before any model work.
    try:
        # Snapshot checks cleanliness before creating anything inside a source checkout.
        base = snapshot(source, workspace)
        budget.step()
        baseline = tools.call("run_tests", {})
        record("run_tests", {}, baseline)
        if not baseline.get("ok") or baseline.get("timed_out") or baseline.get("total", 0) == 0:
            raise RuntimeError(
                "Baseline could not execute a test suite. Check runner setup and tests/ before using a model."
            )
        if hasattr(provider, "start"):
            provider.start(baseline)
        # Phase 2 alternates proposed actions with observed tool results.
        while True:
            if budget.steps >= budget.max_steps:
                raise BudgetExceeded("Tool step budget exhausted")
            action = provider.next(previous, budget)
            if action is None:
                error = "Provider stopped before producing a validated patch"
                failure_mode = "provider_stopped"
                break
            budget.step()
            previous = tools.call(action["name"], action["arguments"])
            record(action["name"], action["arguments"], previous)
            # Only Toolset.finish can approve this transition, never model prose.
            if action["name"] == "finish" and previous.get("ok"):
                status = "awaiting_review"
                break
    except BudgetExceeded as exc:
        status, error, failure_mode = "budget_exhausted", str(exc), "budget"
    except KeyboardInterrupt:
        status, error, failure_mode = "cancelled", "Run interrupted by operator", "cancelled"
    except Exception as exc:
        status, error, failure_mode = "failed", f"{type(exc).__name__}: {exc}", type(exc).__name__
    # Phase 3 persists evidence for successful, failed, and interrupted runs.
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "trace.jsonl").touch(exist_ok=True)
    if base:
        try:
            patch = git(workspace, "diff", "--no-ext-diff", "--no-textconv")
            if patch:
                patch += "\n"
        except Exception as exc:
            status, error, failure_mode = "failed", str(exc), "patch_export"
    (folder / "patch.diff").write_text(patch)
    cost_available = getattr(provider, "cost_available", True)
    result = {
        "run_id": run_id,
        "status": status,
        "provider": provider.name,
        "model": getattr(provider, "model", None),
        "issue": issue,
        "issue_url": issue_url,
        "source": str(source.resolve()),
        "base_commit": base,
        "workspace": str(workspace),
        "artifacts": str(folder),
        "plan": tools.plan,
        "summary": tools.summary,
        "error": error,
        "failure_mode": failure_mode,
        "cost_available": cost_available,
        "usage_known": getattr(provider, "usage_known", True),
        "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
        "validated_tree": tools.validated_tree,
        "test_runs": tools.tests,
        "budget": asdict(budget),
        "provider_retries": getattr(provider, "retries", 0),
        "model_attempts": getattr(provider, "attempts", None),
        "duration_seconds": round(time.monotonic() - started, 3),
    }
    if not cost_available:
        result["budget"]["estimated_cost"] = None
    (folder / "run.json").write_text(json.dumps(result, indent=2) + "\n")
    baseline = tools.tests[0] if tools.tests else {}
    final = tools.tests[-1] if tools.tests else {}
    issue_reference = f"Closes {issue_url}\n\n" if issue_url else ""
    (folder / "pr.md").write_text(
        f"{tools.summary or 'Incomplete maintenance run'}\n\n"
        + issue_reference
        + f"## Approach\n\n{tools.plan}\n\n"
        + "## Validation\n\n"
        + "| Stage | Passing tests |\n| --- | --- |\n"
        + f"| Baseline | {baseline.get('passed', 0)} / {baseline.get('total', 0)} |\n"
        + f"| Final candidate | {final.get('passed', 0)} / {final.get('total', 0)} |\n\n"
        + "Test command `python -m unittest discover -s tests -v`. Tests were kept unchanged by the agent tools.\n\n"
        + f"Provider `{provider.name}`. Run `{run_id}`.\n\n"
        + f"Patch SHA-256 `{result['patch_sha256']}`.\n\n"
        + "Generated by PatchPilot. Review the diff and checks before merging.\n"
    )
    render(folder, result, events, patch)
    (output.resolve() / "latest.json").write_text(
        json.dumps({"run_id": run_id, "artifacts": str(folder)}, indent=2) + "\n"
    )
    return result
