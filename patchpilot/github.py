"""Optional GitHub CLI adapter. Publication is outside the model tool surface."""

import hashlib
import json
from pathlib import Path
import re

from .runtime import PolicyError, command, git


REPO_PATTERN = r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"


def gh(*args: str) -> str:
    """Run GitHub CLI without a shell and convert command failures into policy errors."""
    result = command(["gh", *args], Path.cwd(), timeout=60)
    if result["exit_code"]:
        raise PolicyError(result["output"])
    return result["output"].strip()


def read_issue(url: str) -> dict:
    """Read title and body from a validated github.com issue URL."""
    if not re.fullmatch(r"https://github\.com/" + REPO_PATTERN + r"/issues/[1-9][0-9]*", url):
        raise PolicyError("Expected a github.com issue URL")
    return json.loads(gh("issue", "view", url, "--json", "number,title,body,url"))


def publication_plan(folder: Path, repo: str) -> dict:
    """Bind the reviewed patch and destination into a reproducible approval hash.

    Changing the repository, base, branch, title, body, or patch requires a new
    approval. This is a local integrity check, not authenticated authorization.
    """
    if not re.fullmatch(REPO_PATTERN, repo) or any(p.startswith(".") for p in repo.split("/")):
        raise PolicyError("Expected GitHub owner/repository")
    result = json.loads((folder / "run.json").read_text())
    patch_hash = hashlib.sha256((folder / "patch.diff").read_bytes()).hexdigest()
    if result["status"] != "awaiting_review" or patch_hash != result["patch_sha256"]:
        raise PolicyError("Run must be validated and its patch unchanged")
    if not re.fullmatch(r"[0-9a-f]{40,64}", result["base_commit"]):
        raise PolicyError("Invalid source commit")
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}", result["run_id"]):
        raise PolicyError("Invalid run ID")
    plan = {
        "repository": repo,
        "base_commit": result["base_commit"],
        "branch": "patchpilot/" + result["run_id"],
        "patch_sha256": patch_hash,
        "title": result["issue"].splitlines()[0].lstrip("# ")[:120],
        "body": (folder / "pr.md").read_text(),
        "draft": True,
    }
    plan["approval_sha256"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    (folder / "publish-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    return plan


def publish(folder: Path, repo: str, approval: str) -> str:
    """Publish the approved patch as a draft PR and save a retry receipt.

    The target repository must contain the tested source commit. A stable
    branch name and existing-PR lookup reduce duplicate external effects.
    The model does not have access to this function through the tool registry.
    """
    plan = publication_plan(folder, repo)
    if approval != plan["approval_sha256"]:
        raise PolicyError("Approval must match the exact publication plan hash")
    receipt = folder / "publication.json"
    if receipt.exists():
        saved = json.loads(receipt.read_text())
        if saved["approval_sha256"] != approval:
            raise PolicyError("This run already published a different plan")
        return saved["url"]
    # A retry reuses the same branch and checks for an existing PR first.
    existing = json.loads(
        gh(
            "pr",
            "list",
            "--repo",
            repo,
            "--head",
            plan["branch"],
            "--state",
            "all",
            "--json",
            "url",
        )
    )
    if existing:
        url = existing[0]["url"]
    else:
        target = folder / "publication-workspace"
        if not target.exists():
            result = command(
                ["git", "clone", "--", "https://github.com/" + repo + ".git", str(target)],
                folder,
                timeout=120,
            )
            if result["exit_code"]:
                raise PolicyError(result["output"])
        base_branch = git(target, "symbolic-ref", "refs/remotes/origin/HEAD").removeprefix(
            "refs/remotes/origin/"
        )
        # Avoid publishing a local patch into an unrelated repository history.
        git(target, "merge-base", "--is-ancestor", plan["base_commit"], "origin/" + base_branch)
        remote = git(target, "ls-remote", "--heads", "origin", "refs/heads/" + plan["branch"])
        if not remote:
            git(target, "checkout", "-B", plan["branch"], plan["base_commit"])
            git(target, "apply", "--check", str((folder / "patch.diff").resolve()))
            git(target, "apply", str((folder / "patch.diff").resolve()))
            git(target, "add", "-u")
            git(
                target,
                "-c",
                "user.name=PatchPilot",
                "-c",
                "user.email=patchpilot@example.invalid",
                "commit",
                "-m",
                plan["title"],
            )
            git(target, "push", "origin", plan["branch"])
        else:
            git(target, "fetch", "origin", plan["branch"])
            if git(target, "rev-parse", "FETCH_HEAD^") != plan["base_commit"]:
                raise PolicyError("Existing remote branch has a different base")
            remote_patch = git(
                target, "diff", "--no-ext-diff", "--no-textconv", plan["base_commit"], "FETCH_HEAD"
            )
            if remote_patch != (folder / "patch.diff").read_text().strip():
                raise PolicyError("Existing remote branch differs from approved patch")
        url = gh(
            "pr",
            "create",
            "--repo",
            repo,
            "--head",
            plan["branch"],
            "--base",
            base_branch,
            "--draft",
            "--title",
            plan["title"],
            "--body-file",
            str((folder / "pr.md").resolve()),
        )
    receipt.write_text(json.dumps({"approval_sha256": approval, "url": url}, indent=2) + "\n")
    return url
