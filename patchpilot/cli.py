"""CLI entry points. Offline demo needs only Python and Git."""
import argparse
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile

from .agent import run
from .github import publication_plan, publish, read_issue
from .mcp import Server
from .providers import Budget, OpenAIProvider, ScriptedProvider
from .runtime import PolicyError, init_repository
from .tools import Toolset

ROOT = Path(__file__).resolve().parent.parent


def demo(task: str, output: Path, runner="local"):
    fixture = ROOT / "examples" / task
    with tempfile.TemporaryDirectory(prefix="patchpilot-demo-") as temporary:
        source = Path(temporary) / "repo"
        shutil.copytree(fixture, source, ignore=shutil.ignore_patterns("__pycache__", "actions.json", "issue.md"))
        init_repository(source)
        provider = ScriptedProvider(json.loads((fixture / "actions.json").read_text()))
        return run(source, (fixture / "issue.md").read_text(), provider, output, runner)


def main(argv=None):
    parser = argparse.ArgumentParser(description="PatchPilot maintenance agent")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("demo", help="Run a scripted repair against a seeded bug")
    d.add_argument("--task", choices=["cart", "slug"], default="cart")
    d.add_argument("--runner", choices=["local", "docker"], default="local")
    d.add_argument("--output", type=Path, default=Path("runs"))
    ev = sub.add_parser("eval", help="Evaluate both scripted golden tasks")
    ev.add_argument("--output", type=Path, default=Path("runs/evaluation"))
    ev.add_argument("--runner", choices=["local", "docker"], default="local")
    live = sub.add_parser("run", help="Use a live model against a clean Python Git repository")
    live.add_argument("--repo", type=Path, required=True)
    issue = live.add_mutually_exclusive_group(required=True)
    issue.add_argument("--issue", type=Path)
    issue.add_argument("--github-issue")
    live.add_argument("--model", required=True)
    live.add_argument("--runner", choices=["local", "docker"], default="docker")
    live.add_argument("--trust-local-code", action="store_true")
    live.add_argument("--output", type=Path, default=Path("runs"))
    live.add_argument("--max-steps", type=int, default=24)
    live.add_argument("--max-tokens", type=int, default=40000)
    live.add_argument("--max-cost", type=float, default=1.0)
    live.add_argument("--input-rate", type=float, required=True, help="USD per million input tokens")
    live.add_argument("--output-rate", type=float, required=True, help="USD per million output tokens")
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
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = demo(args.task, args.output, args.runner)
        elif args.command == "eval":
            results = [demo(task, args.output, args.runner) for task in ["cart", "slug"]]
            successful = sum(r["status"] == "awaiting_review" for r in results)
            result = {"provider": "scripted", "tasks": len(results), "successful": successful,
                      "success_rate": successful / len(results),
                      "note": "Pipeline regression results, not autonomous model performance",
                      "runs": [{"run_id": r["run_id"], "status": r["status"], "artifacts": r["artifacts"],
                                "duration_seconds": r["duration_seconds"], "error": r["error"]} for r in results]}
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2))
            return 0 if successful == len(results) else 1
        elif args.command == "run":
            if args.runner == "local" and not args.trust_local_code:
                raise PolicyError("Local tests execute repository code. Pass --trust-local-code or use Docker.")
            numbers = [args.max_steps, args.max_tokens, args.max_cost, args.input_rate, args.output_rate]
            if any(not math.isfinite(n) or n <= 0 for n in numbers):
                raise ValueError("Budget limits and live model rates must be positive finite numbers")
            if args.issue:
                issue_text = args.issue.read_text()
            else:
                item = read_issue(args.github_issue)
                issue_text = item["title"] + "\n\n" + item["body"]
            budget = Budget(args.max_steps, args.max_tokens, args.max_cost, args.input_rate, args.output_rate)
            result = run(args.repo, issue_text, OpenAIProvider(issue_text, args.model), args.output, args.runner, budget)
        elif args.command == "mcp":
            Server(Toolset(args.repo, args.runner), args.allow_execution).serve()
            return 0
        elif args.command == "publish-plan":
            print(json.dumps(publication_plan(args.run.resolve(), args.repo), indent=2))
            return 0
        else:
            print(publish(args.run.resolve(), args.repo, args.approve))
            return 0
        print(json.dumps({key: result[key] for key in ["run_id", "status", "artifacts", "error"]}, indent=2))
        return 0 if result["status"] == "awaiting_review" else 1
    except (ValueError, OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
