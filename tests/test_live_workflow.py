import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from patchpilot.agent import run
from patchpilot.cli import demo
from patchpilot.codex_provider import CodexProvider
from patchpilot.providers import Budget, ScriptedProvider
from patchpilot.review import apply_plan, apply_patch
from patchpilot.runtime import PolicyError, command, git, init_repository
from patchpilot.tools import Toolset


class LiveWorkflowTests(unittest.TestCase):
    def test_approved_patch_applies_to_original_and_passes_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = demo("cart", Path(tmp))
            source, folder = Path(result["source"]), Path(result["artifacts"])
            self.assertIn("return int(amount)", (source / "cart.py").read_text())
            plan = apply_plan(folder, source)
            with self.assertRaises(PolicyError):
                apply_patch(folder, source, "wrong-hash")
            receipt = apply_patch(folder, source, plan["approval_sha256"])
            self.assertEqual(receipt["status"], "applied")
            self.assertFalse(receipt["committed"])
            self.assertTrue(Toolset(source).run_tests()["success"])
            self.assertIn("cart.py", git(source, "diff", "--name-only"))
            with self.assertRaises(PolicyError):
                apply_patch(folder, source, plan["approval_sha256"])

    def test_target_changes_invalidate_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = demo("slug", Path(tmp))
            source, folder = Path(result["source"]), Path(result["artifacts"])
            plan = apply_plan(folder, source)
            (source / "slug.py").write_text("changed")
            with self.assertRaises(PolicyError):
                apply_patch(folder, source, plan["approval_sha256"])

    def test_setup_failure_preserves_a_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run(Path(tmp) / "missing", "Fix bug", ScriptedProvider([]), Path(tmp) / "runs")
            self.assertEqual(result["status"], "failed")
            self.assertTrue((Path(result["artifacts"]) / "report.html").exists())
            self.assertIsNone(result["validated_tree"])

    def test_missing_suite_stops_before_any_model_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            (root / "code.py").write_text("value = 1\n")
            init_repository(root)
            provider = ScriptedProvider([])
            with patch.object(provider, "next") as next_call:
                result = run(root, "Fix bug", provider, Path(tmp) / "runs")
            next_call.assert_not_called()
            self.assertEqual(result["status"], "failed")
            self.assertIn("Baseline", result["error"])

    def test_codex_uses_observed_failure_for_second_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            (root / "calc.py").write_text("def add(a, b):\n    return a - b\n")
            (root / "tests").mkdir()
            (root / "tests/test_calc.py").write_text(
                "import unittest\nfrom calc import add\nclass T(unittest.TestCase):\n"
                " def test_add(self): self.assertEqual(add(2, 3), 5)\n")
            init_repository(root)
            proposals = [
                {"plan": "Try multiplication", "summary": "First candidate", "edits": [
                    {"path": "calc.py", "old": "a - b", "new": "a * b"}]},
                {"plan": "Fix addition after failure", "summary": "Addition fixed", "edits": [
                    {"path": "calc.py", "old": "a * b", "new": "a + b"}]},
            ]
            with patch("shutil.which", return_value="codex"):
                provider = CodexProvider("Fix addition")
            observed = []
            def propose(budget):
                observed.append(json.loads(json.dumps(provider.feedback)))
                return proposals.pop(0)
            with patch.object(provider, "propose", side_effect=propose):
                result = run(root, "Fix addition", provider, Path(tmp) / "runs")
            self.assertEqual(result["status"], "awaiting_review")
            self.assertEqual(result["model_attempts"], 2)
            self.assertEqual([t["success"] for t in result["test_runs"]], [False, False, True])
            self.assertFalse(observed[1][-1]["tests"]["success"])
            self.assertIsNone(result["budget"]["estimated_cost"])
            self.assertIn("Not reported", (Path(result["artifacts"]) / "report.html").read_text())
            self.assertEqual((root / "calc.py").read_text(), "def add(a, b):\n    return a - b\n")

    def test_codex_adapter_parses_real_cli_shape_without_tools(self):
        with patch("shutil.which", return_value="codex"):
            provider = CodexProvider("Fix addition")
        provider.files = {"calc.py": "return a - b"}
        proposal = {"plan": "Fix", "summary": "Fixed", "edits": [{"path": "calc.py", "old": "a - b", "new": "a + b"}]}
        def mock_command(argv, cwd, timeout, input_text):
            self.assertIn("--ignore-user-config", argv)
            self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
            self.assertIn("shell_tool", argv)
            self.assertIn("multi_agent", argv)
            self.assertIn("Fix addition", input_text)
            Path(argv[argv.index("--output-last-message") + 1]).write_text(json.dumps(proposal))
            return {"exit_code": 0, "timed_out": False, "output": json.dumps({
                "type": "turn.completed", "usage": {"input_tokens": 80, "output_tokens": 30}})}
        budget = Budget()
        with patch("patchpilot.codex_provider.command", side_effect=mock_command):
            self.assertEqual(provider.propose(budget), proposal)
        self.assertEqual(budget.input_tokens, 80)

    def test_codex_timeout_is_not_retried(self):
        with patch("shutil.which", return_value="codex"):
            provider = CodexProvider("Fix bug")
        with patch("patchpilot.codex_provider.command", return_value={"timed_out": True}) as execute:
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                provider.propose(Budget())
            self.assertEqual(execute.call_count, 1)
        self.assertFalse(provider.usage_known)

    def test_command_supports_stdin(self):
        import sys
        result = command([sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"], Path.cwd(), input_text="hello")
        self.assertEqual(result["output"].strip(), "HELLO")
