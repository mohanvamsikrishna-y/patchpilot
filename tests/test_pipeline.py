"""Controller integration tests for golden tasks, budgets, and publication approval checks."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from patchpilot.agent import run
from patchpilot.cli import demo
from patchpilot.github import publication_plan, publish
from patchpilot.providers import Budget, BudgetExceeded, ScriptedProvider
from patchpilot.runtime import PolicyError, init_repository


class PipelineTests(unittest.TestCase):
    def test_demo_repairs_without_changing_original_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = demo("cart", Path(tmp))
            self.assertEqual(result["status"], "awaiting_review")
            self.assertEqual([t["success"] for t in result["test_runs"]], [False, False, True])
            self.assertEqual(result["test_runs"][-1]["passed"], 5)
            folder = Path(result["artifacts"])
            patch = (folder / "patch.diff").read_text()
            self.assertIn("ROUND_HALF_UP", patch)
            self.assertNotIn("tests/", patch)
            self.assertTrue((folder / "report.html").exists())
            self.assertEqual(result["patch_sha256"], hashlib.sha256(patch.encode()).hexdigest())
            plan = publication_plan(folder, "example/project")
            self.assertTrue(plan["draft"])
            with self.assertRaises(PolicyError):
                publish(folder, "example/project", "not-approved")
            (folder / "patch.diff").write_text(patch + "tampered")
            with self.assertRaises(PolicyError):
                publication_plan(folder, "example/project")

    def test_slug_golden_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = demo("slug", Path(tmp))
            self.assertEqual(result["status"], "awaiting_review")
            self.assertEqual(result["test_runs"][-1]["passed"], 5)

    def test_budget_failure_retains_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "x.py").write_text("x = 1\n")
            init_repository(source)
            (source / "tests").mkdir()
            (source / "tests/test_x.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n"
            )
            from patchpilot.runtime import git

            git(source, "add", ".")
            git(
                source,
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-m",
                "Add suite",
            )
            result = run(
                source, "fix", ScriptedProvider([]), Path(tmp) / "runs", budget=Budget(max_steps=1)
            )
            self.assertEqual(result["status"], "budget_exhausted")
            self.assertTrue((Path(result["artifacts"]) / "trace.jsonl").exists())

    def test_no_actions_does_not_claim_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "x.py").write_text("x = 1\n")
            init_repository(source)
            result = run(source, "fix", ScriptedProvider([]), Path(tmp) / "runs")
            self.assertEqual(result["status"], "failed")

    def test_token_and_cost_reservations(self):
        with self.assertRaises(BudgetExceeded):
            Budget(max_tokens=10).reserve(8, 3)
        with self.assertRaises(BudgetExceeded):
            Budget(max_cost=0.01, input_rate=10).reserve(2000, 0)
        budget = Budget(input_rate=2, output_rate=8)
        budget.charge({"input_tokens": 100, "output_tokens": 50})
        self.assertAlmostEqual(budget.estimated_cost, 0.0006)
