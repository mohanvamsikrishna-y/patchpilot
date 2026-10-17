"""CLI entry points. Offline demo needs only Python and Git."""

import argparse
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import webbrowser

from .agent import run
from .codex_provider import CodexProvider
from .doctor import inspect_environment
from .review import apply_plan, apply_patch, load_review
from .github import publication_plan, publish, read_issue
from .mcp import Server
from .providers import Budget, OpenAIProvider, ScriptedProvider
from .runtime import PolicyError, init_repository
from .tools import Toolset

ROOT = Path(__file__).resolve().parent.parent


def progress(event):
    """Print a short tool observation to stderr, leaving stdout for JSON results."""
    name, result = event["tool"], event["result"]
    detail = ""
    if name == "run_tests":
        detail = f"{result.get('passed', 0)}/{result.get('total', 0)} tests passed"
        if not result.get("success"):
            detail += " · validation failed"
    elif name == "read_file":
        detail = event["arguments"]["path"]
    elif name == "replace_text":
        detail = event["arguments"]["path"]
    elif name == "record_plan":
        detail = result.get("plan", "")
    elif name == "finish":
        detail = result.get("status", "")
    if not result.get("ok"):
        detail = result.get("message", result.get("error", "Tool failed"))
    print(f"  {event['step']:02}  {name:<15} {detail}", file=sys.stderr, flush=True)


def demo(
    task: str,
    output: Path,
    runner="local",
    provider_name="scripted",
    model=None,
    on_event=None,
    budget=None,
):
    """Create a retained demo checkout, choose a provider, and run the controller.

    The model receives source, tests, and the issue. The scripted action file
    stays outside that checkout and is loaded only by the scripted provider.
    """
    fixture = ROOT / "examples" / task
    # The source survives the run so the interviewer can inspect and apply the patch.
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = Path(tempfile.mkdtemp(prefix=f"{task}-source-", dir=output))
    shutil.copytree(
        fixture,
        source,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "actions.json", "issue.md"),
    )
    init_repository(source)
    issue = (fixture / "issue.md").read_text()
    if provider_name == "scripted":
        provider = ScriptedProvider(json.loads((fixture / "actions.json").read_text()))
    elif provider_name == "codex":
        provider = CodexProvider(issue, model)
    else:
        if not model:
            raise ValueError("--model is required for the OpenAI provider")
        provider = OpenAIProvider(issue, model)
    return run(source, issue, provider, output, runner, budget, on_event)


def main(argv=None):
    """Parse CLI options, dispatch one workflow, and return a process exit code.

    Commands are grouped into demo/evaluation, live execution, local review,
    MCP transport, and GitHub publication. A validated run exits with zero;
    an incomplete run exits with one and retains its diagnostic artifacts.
    """
    parser = argparse.ArgumentParser(description="PatchPilot maintenance agent")
    # Configure command inputs here; implementation lives in focused modules.
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("demo", help="Repair a seeded bug with a scripted or live Codex provider")
    d.add_argument("--provider", choices=["scripted", "codex"], default="scripted")
    d.add_argument("--model")
    d.add_argument("--open", action="store_true", help="Open the final report in your browser")
    d.add_argument("--quiet", action="store_true")
    d.add_argument("--task", choices=["cart", "slug"], default="cart")
    d.add_argument("--runner", choices=["local", "docker"], default="local")
    d.add_argument("--output", type=Path, default=Path("runs"))
    ev = sub.add_parser("eval", help="Evaluate both scripted golden tasks")
    ev.add_argument("--provider", choices=["scripted", "codex"], default="scripted")
    ev.add_argument("--model")
    ev.add_argument("--output", type=Path, default=Path("runs/evaluation"))
    ev.add_argument("--runner", choices=["local", "docker"], default="local")
    live = sub.add_parser("run", help="Use a live model against a clean Python Git repository")
    live.add_argument("--repo", type=Path, required=True)
    issue = live.add_mutually_exclusive_group(required=True)
    issue.add_argument("--issue", type=Path)
    issue.add_argument("--github-issue")
    live.add_argument("--provider", choices=["openai", "codex"], default="codex")
    live.add_argument("--model")
    live.add_argument("--open", action="store_true")
    live.add_argument("--quiet", action="store_true")
    live.add_argument("--test-timeout", type=float, default=30)
    live.add_argument("--runner", choices=["local", "docker"], default="docker")
    live.add_argument("--trust-local-code", action="store_true")
    live.add_argument("--output", type=Path, default=Path("runs"))
    live.add_argument("--max-steps", type=int, default=24)
    live.add_argument("--max-tokens", type=int, default=40000)
    live.add_argument("--max-cost", type=float, default=1.0)
    live.add_argument("--input-rate", type=float, default=0, help="USD per million input tokens")
    live.add_argument("--output-rate", type=float, default=0, help="USD per million output tokens")
    sub.add_parser("doctor", help="Check demo and optional integration readiness")
    review = sub.add_parser("review", help="Inspect a validated patch and its approval plan")
    review.add_argument("--run", type=Path, required=True)
    review.add_argument("--target", type=Path)
    review.add_argument("--open", action="store_true")
    apply = sub.add_parser("apply", help="Apply an approved patch without committing or pushing")
    apply.add_argument("--run", type=Path, required=True)
    apply.add_argument("--target", type=Path, required=True)
    apply.add_argument("--approve", required=True)
    m = sub.add_parser("mcp", help="Start the MCP stdio tools server")
    m.add_argument("--repo", type=Path, required=True)
    m.add_argument("--runner", choices=["local", "docker"], default="docker")
    m.add_argument("--allow-execution", action="store_true")
    for name in ["publish-plan", "publish"]:
        p = sub.add_parser(name)
        p.add_argument("--run", type=Path, required=True)
        p.add_argument("--repo", required=True)
        if name == "publish":
            p.add_argument("--approve", required=True)
    # Dispatch one command. The CLI never decides whether a patch is valid.
    args = parser.parse_args(argv)
    try:
        if hasattr(args, "run") and str(args.run) == "latest":
            args.run = Path(json.loads(Path("runs/latest.json").read_text())["artifacts"])
        if args.command == "demo":
            print(f"PatchPilot · {args.provider} provider · {args.runner} tests", file=sys.stderr)
            result = demo(
                args.task,
                args.output,
                args.runner,
                args.provider,
                args.model,
                None if args.quiet else progress,
            )
        elif args.command == "eval":
            results = [
                demo(task, args.output, args.runner, args.provider, args.model, progress)
                for task in ["cart", "slug"]
            ]
            successful = sum(r["status"] == "awaiting_review" for r in results)
            result = {
                "provider": args.provider,
                "tasks": len(results),
                "successful": successful,
                "success_rate": successful / len(results),
                "note": (
                    "Scripted pipeline regression results"
                    if args.provider == "scripted"
                    else "Two seeded tasks only; not a general model benchmark"
                ),
                "runs": [
                    {
                        "run_id": r["run_id"],
                        "status": r["status"],
                        "artifacts": r["artifacts"],
                        "duration_seconds": r["duration_seconds"],
                        "error": r["error"],
                    }
                    for r in results
                ],
            }
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2))
            return 0 if successful == len(results) else 1
        elif args.command == "run":
            if args.runner == "local" and not args.trust_local_code:
                raise PolicyError(
                    "Local tests execute repository code. Pass --trust-local-code or use Docker."
                )
            numbers = [args.max_steps, args.max_tokens, args.max_cost, args.test_timeout]
            if args.provider == "openai":
                numbers.extend([args.input_rate, args.output_rate])
                if not args.model:
                    raise ValueError("--model is required for the OpenAI provider")
            if any(not math.isfinite(n) or n <= 0 for n in numbers):
                raise ValueError(
                    "Budget limits and live model rates must be positive finite numbers"
                )
            if args.issue:
                issue_text = args.issue.read_text()
            else:
                item = read_issue(args.github_issue)
                issue_text = item["title"] + "\n\n" + item["body"]
            budget = Budget(
                args.max_steps, args.max_tokens, args.max_cost, args.input_rate, args.output_rate
            )
            provider = (
                CodexProvider(issue_text, args.model)
                if args.provider == "codex"
                else OpenAIProvider(issue_text, args.model)
            )
            result = run(
                args.repo,
                issue_text,
                provider,
                args.output,
                args.runner,
                budget,
                None if args.quiet else progress,
                args.test_timeout,
            )
        elif args.command == "doctor":
            checks = inspect_environment()
            for check in checks:
                print(
                    f"{'READY' if check['ready'] else 'OPTIONAL / MISSING':<20} {check['name']} · {check['detail']}"
                )
            print(
                "Offline demo needs Python and Git. Live Codex mode additionally needs Codex sign-in."
            )
            return 0 if all(c["ready"] for c in checks[:2]) else 1
        elif args.command == "review":
            result, patch = load_review(args.run)
            print(patch)
            target = args.target or Path(result["source"])
            print(json.dumps(apply_plan(args.run, target), indent=2))
            if args.open:
                webbrowser.open((args.run.resolve() / "report.html").as_uri())
            return 0
        elif args.command == "apply":
            print(json.dumps(apply_patch(args.run, args.target, args.approve), indent=2))
            return 0
        elif args.command == "mcp":
            Server(Toolset(args.repo, args.runner), args.allow_execution).serve()
            return 0
        elif args.command == "publish-plan":
            print(json.dumps(publication_plan(args.run.resolve(), args.repo), indent=2))
            return 0
        else:
            print(publish(args.run.resolve(), args.repo, args.approve))
            return 0
        print(
            json.dumps(
                {key: result[key] for key in ["run_id", "status", "artifacts", "error"]}, indent=2
            )
        )
        if getattr(args, "open", False):
            webbrowser.open((Path(result["artifacts"]) / "report.html").as_uri())
        print(f"Report · {result['artifacts']}/report.html", file=sys.stderr)
        return 0 if result["status"] == "awaiting_review" else 1
    except (ValueError, OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
