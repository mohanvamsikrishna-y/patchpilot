"""Exercise Git publication against a real local bare remote without network writes."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from patchpilot.agent import run
from patchpilot.demo_workspace import prepare
from patchpilot.github import publication_plan, publish, validate_branch
from patchpilot.providers import ScriptedProvider
from patchpilot.runtime import PolicyError, command, git


class GitHubWorkflowTests(unittest.TestCase):
    def test_local_preparation_excludes_scripted_answers_and_keeps_main_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = prepare("cart", Path(tmp) / "demo", branch="patchpilot-demo/cart")
            root = Path(manifest["source"])
            self.assertFalse((root / "actions.json").exists())
            self.assertFalse((root / "issue.md").exists())
            self.assertTrue((root / ".github/workflows/validate.yml").exists())
            self.assertEqual(git(root, "branch", "--show-current"), "patchpilot-demo/cart")
            self.assertFalse(manifest["pushed"])
            with self.assertRaises(PolicyError):
                prepare("cart", Path(tmp) / "demo")

    def test_explicit_base_and_publication_retry_with_real_git_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            manifest = prepare("cart", folder / "demo", branch="patchpilot-demo/cart")
            source = Path(manifest["source"])
            remote = folder / "remote.git"
            result = command(["git", "init", "--bare", str(remote)], folder)
            self.assertEqual(result["exit_code"], 0)
            git(source, "remote", "add", "origin", str(remote))
            git(source, "push", "origin", "HEAD:refs/heads/patchpilot-demo/cart")
            actions = json.loads((Path("examples/cart/actions.json")).read_text())
            result = run(
                source, "Repair checkout rounding", ScriptedProvider(actions), folder / "runs"
            )
            artifacts = Path(result["artifacts"])
            plan = publication_plan(artifacts, "example/project", "patchpilot-demo/cart")
            default_plan = publication_plan(artifacts, "example/project")
            self.assertNotEqual(plan["approval_sha256"], default_plan["approval_sha256"])
            with self.assertRaises(PolicyError):
                publish(artifacts, "example/project", plan["approval_sha256"], "other-branch")
            calls = []

            def fake_gh(*args):
                calls.append(args)
                if args[:2] == ("pr", "list"):
                    return "[]"
                if args[:2] == ("pr", "create"):
                    self.assertEqual(args[args.index("--base") + 1], "patchpilot-demo/cart")
                    self.assertEqual(
                        Path(args[args.index("--body-file") + 1]).read_text(), plan["body"]
                    )
                    return "https://github.com/example/project/pull/1"
                raise AssertionError(args)

            def local_command(argv, cwd, **kwargs):
                if argv[:2] == ["git", "clone"]:
                    argv = [
                        str(remote) if a == "https://github.com/example/project.git" else a
                        for a in argv
                    ]
                return command(argv, cwd, **kwargs)

            with patch("patchpilot.github.gh", side_effect=fake_gh):
                with patch("patchpilot.github.command", side_effect=local_command):
                    url = publish(
                        artifacts,
                        "example/project",
                        plan["approval_sha256"],
                        "patchpilot-demo/cart",
                    )
                    # Repeating the exact approved operation returns the receipt.
                    self.assertEqual(
                        publish(
                            artifacts,
                            "example/project",
                            plan["approval_sha256"],
                            "patchpilot-demo/cart",
                        ),
                        url,
                    )
            self.assertEqual(sum(c[:2] == ("pr", "create") for c in calls), 1)
            clone = folder / "inspect"
            command(["git", "clone", "--branch", plan["branch"], str(remote), str(clone)], folder)
            self.assertIn("amount.quantize", (clone / "cart.py").read_text())
            self.assertEqual(git(clone, "rev-parse", "HEAD^"), manifest["base_commit"])
            # No ref was created for main by the maintenance publisher.
            self.assertEqual(git(source, "ls-remote", "--heads", "origin", "refs/heads/main"), "")
            # Simulate losing the local receipt after pushing, before PR creation.
            (artifacts / "publication.json").unlink()
            with patch("patchpilot.github.gh", side_effect=fake_gh):
                self.assertEqual(
                    publish(
                        artifacts,
                        "example/project",
                        plan["approval_sha256"],
                        "patchpilot-demo/cart",
                    ),
                    url,
                )
            self.assertEqual(git(clone, "rev-parse", "HEAD^"), manifest["base_commit"])

            # Lost receipt with an existing PR still checks its destination.
            (artifacts / "publication.json").unlink()
            with patch(
                "patchpilot.github.gh",
                return_value=json.dumps([{"url": url, "baseRefName": "patchpilot-demo/cart"}]),
            ):
                self.assertEqual(
                    publish(
                        artifacts,
                        "example/project",
                        plan["approval_sha256"],
                        "patchpilot-demo/cart",
                    ),
                    url,
                )
            (artifacts / "publication.json").unlink()
            with patch(
                "patchpilot.github.gh",
                return_value=json.dumps([{"url": url, "baseRefName": "unapproved-target"}]),
            ):
                with self.assertRaises(PolicyError):
                    publish(
                        artifacts,
                        "example/project",
                        plan["approval_sha256"],
                        "patchpilot-demo/cart",
                    )

    def test_rejects_invalid_branch_names(self):
        for branch in ["--force", "../main", "main..other", "HEAD", "has space", "x.lock"]:
            with self.subTest(branch=branch), self.assertRaises(PolicyError):
                validate_branch(branch)

    def test_github_warning_does_not_corrupt_structured_stdout(self):
        from patchpilot.github import gh, validate_pr_url
        import sys

        def warning_command(argv, cwd, **kwargs):
            return command(
                [
                    sys.executable,
                    "-c",
                    "import sys; print('warning', file=sys.stderr); print('https://github.com/example/project/pull/1')",
                ],
                cwd,
                **kwargs,
            )

        with patch("patchpilot.github.command", side_effect=warning_command):
            self.assertEqual(gh("pr", "create"), "https://github.com/example/project/pull/1")
        with self.assertRaises(PolicyError):
            validate_pr_url("warning\nhttps://github.com/example/project/pull/1", "example/project")

    def test_one_command_workflow_prepares_bound_review_plan(self):
        from patchpilot.demo_workspace import execute

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "workflow"

            def local_prepare(task, destination, repository, **kwargs):
                self.assertTrue(kwargs["push"])
                self.assertTrue(kwargs["create_issue"])
                manifest = prepare(task, destination, branch="patchpilot-demo/test")
                manifest["issue_url"] = "https://github.com/example/project/issues/1"
                return manifest

            actions = json.loads(Path("examples/cart/actions.json").read_text())
            with (
                patch("patchpilot.demo_workspace.shutil.which", return_value="codex"),
                patch("patchpilot.demo_workspace.prepare", side_effect=local_prepare),
                patch(
                    "patchpilot.github.read_issue",
                    return_value={
                        "title": "Fix checkout cents",
                        "body": "Use half-up rounding",
                        "url": "https://github.com/example/project/issues/1",
                    },
                ),
                patch(
                    "patchpilot.codex_provider.CodexProvider",
                    return_value=ScriptedProvider(actions),
                ),
            ):
                result, workflow = execute("cart", output, "example/project")
            self.assertEqual(result["status"], "awaiting_review")
            self.assertEqual(result["issue_url"], workflow["issue_url"])
            self.assertIn("--base patchpilot-demo/test", workflow["publish_command"])
            self.assertIn("--approve", workflow["publish_command"])
            self.assertTrue((output / "workflow.json").exists())
            self.assertIn(
                "Closes https://github.com/example/project/issues/1",
                (Path(result["artifacts"]) / "pr.md").read_text(),
            )
