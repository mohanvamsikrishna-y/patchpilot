"""Prepare a real repository branch for repeatable GitHub maintenance demos."""

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from .github import gh, validate_repository, validate_branch
from .runtime import PolicyError, command, git, init_repository

FIXTURES = Path(__file__).resolve().parent.parent / "examples"

WORKFLOW = """name: Validate maintenance patch
on:
  pull_request:
permissions:
  contents: read
jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python -m unittest discover -s tests -v
"""


def prepare(
    task: str,
    output: Path,
    repository: str | None = None,
    branch: str | None = None,
    push=False,
    create_issue=False,
) -> dict:
    """Create an isolated task checkout, optionally publish its branch and issue.

    Remote writes require explicit CLI flags. The branch contains only the
    bundled task, its tests, and a validation workflow. Main is never checked out
    or changed. A manifest retains the paths needed by subsequent commands.
    """
    if task not in {"cart", "slug"}:
        raise PolicyError("Unknown demo task")
    if repository:
        validate_repository(repository)
    if (push or create_issue) and not repository:
        raise PolicyError("A GitHub repository is required for remote demo setup")
    if create_issue and not push:
        raise PolicyError("Publish the demo branch before creating its issue")
    branch = branch or "patchpilot-demo/" + task + "-" + datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%f"
    )
    validate_branch(branch)
    output = output.resolve()
    if output.exists():
        raise PolicyError("Choose a new output folder; existing demo work is never overwritten")
    # Verify the destination before creating local files or writing remotely.
    remote = "https://github.com/" + repository + ".git" if repository else None
    if remote:
        gh("repo", "view", repository, "--json", "nameWithOwner")
    output.mkdir(parents=True)
    source = output / "source"
    shutil.copytree(
        FIXTURES / task,
        source,
        ignore=shutil.ignore_patterns("__pycache__", "actions.json", "issue.md"),
    )
    workflow = source / ".github/workflows/validate.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(WORKFLOW)
    (source / "README.md").write_text(
        "# PatchPilot maintenance task\n\nThis branch is an isolated checkout for the "
        + task
        + " maintenance task. The baseline contains an intentional regression. "
        "A generated repair must pass the unchanged unittest suite before review.\n"
    )
    init_repository(source)
    git(source, "branch", "-m", branch)
    issue_text = (FIXTURES / task / "issue.md").read_text()
    issue_file = output / "issue.md"
    issue_file.write_text(issue_text)
    manifest = {
        "task": task,
        "source": str(source),
        "issue_file": str(issue_file),
        "repository": repository,
        "base_branch": branch,
        "base_commit": git(source, "rev-parse", "HEAD"),
        "pushed": False,
        "issue_url": None,
    }

    def save():
        """Keep recovery information even if a later GitHub operation fails."""
        (output / "demo.json").write_text(json.dumps(manifest, indent=2) + "\n")

    save()
    if remote:
        git(source, "remote", "add", "origin", remote)
    if push:
        if git(source, "ls-remote", "--heads", "origin", "refs/heads/" + branch):
            raise PolicyError("Remote branch already exists; choose a new demo branch")
        git(source, "push", "-u", "origin", "HEAD:refs/heads/" + branch)
        manifest["pushed"] = True
        save()
    if create_issue:
        body_file = output / "github-issue.md"
        body_file.write_text(
            issue_text + "\n\nTarget branch `" + branch + "`.\n\n"
            "This issue exercises PatchPilot's real GitHub issue-to-patch workflow. "
            "Keep tests unchanged and submit a draft PR into the target branch.\n"
        )
        manifest["issue_url"] = gh(
            "issue",
            "create",
            "--repo",
            repository,
            "--title",
            issue_text.splitlines()[0],
            "--body-file",
            str(body_file),
        )
        save()
    return manifest


def execute(task: str, output: Path, repository: str, model=None, runner="local", on_event=None):
    """Run setup, real issue intake, live repair, and publication-plan preparation.

    Publication remains a separate command so the operator can inspect the
    generated diff and explicitly approve its exact destination and contents.
    """
    import shlex
    from .agent import run
    from .codex_provider import CodexProvider
    from .github import publication_plan, read_issue

    if not shutil.which("codex"):
        raise PolicyError("Install Codex CLI and sign in before creating a GitHub demo")
    manifest = prepare(task, output / "task", repository, push=True, create_issue=True)
    issue = read_issue(manifest["issue_url"])
    issue_text = issue["title"] + "\n\n" + (issue["body"] or "")
    result = run(
        Path(manifest["source"]),
        issue_text,
        CodexProvider(issue_text, model),
        output / "runs",
        runner,
        on_event=on_event,
        issue_url=issue["url"],
    )
    workflow = {
        "repository": repository,
        "base_branch": manifest["base_branch"],
        "issue_url": issue["url"],
        "artifacts": result["artifacts"],
        "status": result["status"],
    }
    if result["status"] == "awaiting_review":
        plan = publication_plan(Path(result["artifacts"]), repository, manifest["base_branch"])
        workflow["publish_command"] = shlex.join(
            [
                "python3",
                "-m",
                "patchpilot",
                "publish",
                "--run",
                result["artifacts"],
                "--repo",
                repository,
                "--base",
                manifest["base_branch"],
                "--approve",
                plan["approval_sha256"],
            ]
        )
    (output / "workflow.json").write_text(json.dumps(workflow, indent=2) + "\n")
    return result, workflow
