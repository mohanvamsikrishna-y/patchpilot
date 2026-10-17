"""Tool policy tests for repository boundaries, protected tests, edit replay, and validation freshness."""

from pathlib import Path
import tempfile
import unittest

from patchpilot.runtime import PolicyError, init_repository, safe_path, snapshot
from patchpilot.tools import Toolset


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "calc.py").write_text("def add(a, b):\n    return a - b\n")
        (self.root / "tests").mkdir()
        (self.root / "tests/test_calc.py").write_text(
            "import unittest\nfrom calc import add\nclass T(unittest.TestCase):\n"
            "    def test_add(self): self.assertEqual(add(2, 3), 5)\n"
        )
        init_repository(self.root)
        self.tools = Toolset(self.root)

    def prepare(self):
        self.tools.call("read_file", {"path": "calc.py"})
        self.tools.call("record_plan", {"plan": "Replace subtraction with addition"})

    def edit(self, **changes):
        args = {"path": "calc.py", "old": "a - b", "new": "a + b", "operation_id": "op1"}
        return self.tools.call("replace_text", {**args, **changes})

    def test_real_test_execution_and_validated_finish(self):
        self.assertFalse(self.tools.call("run_tests", {})["success"])
        self.prepare()
        self.assertTrue(self.edit()["ok"])
        self.assertTrue(self.tools.call("run_tests", {})["success"])
        self.assertEqual(
            self.tools.call("finish", {"summary": "Fixed addition"})["status"], "awaiting_review"
        )

    def test_requires_inspection_and_plan(self):
        self.assertFalse(self.edit()["ok"])
        self.tools.call("read_file", {"path": "calc.py"})
        self.assertFalse(self.edit()["ok"])

    def test_replay_is_idempotent(self):
        self.prepare()
        self.assertFalse(self.edit()["replayed"])
        self.assertTrue(self.edit()["replayed"])
        self.assertFalse(self.edit(new="a * b")["ok"])

    def test_replay_rejects_stale_file(self):
        self.prepare()
        self.edit()
        (self.root / "calc.py").write_text("changed")
        self.assertFalse(self.edit()["ok"])

    def test_test_files_protected(self):
        self.prepare()
        self.assertFalse(self.edit(path="tests/test_calc.py")["ok"])

    def test_path_escape_and_secret_paths_blocked(self):
        for name in ["../outside.py", "/etc/passwd", ".git/config", ".env", "private.key"]:
            with self.subTest(name=name):
                self.assertFalse(self.tools.call("read_file", {"path": name})["ok"])

    def test_symlink_escape_blocked(self):
        (self.root / "escape.py").symlink_to("/etc/passwd")
        with self.assertRaises(PolicyError):
            safe_path(self.root, "escape.py")

    def test_arguments_are_validated(self):
        for args in [{"query": 5}, {"query": "", "extra": "x"}, {}, None]:
            self.assertFalse(self.tools.call("search", args)["ok"])
        self.assertFalse(self.tools.call("shell", {})["ok"])

    def test_stale_validation_rejected(self):
        self.prepare()
        self.edit()
        self.tools.call("run_tests", {})
        (self.root / "calc.py").write_text("def add(a,b): return 0\n")
        self.assertFalse(self.tools.call("finish", {"summary": "done"})["ok"])

    def test_no_tests_cannot_validate(self):
        (self.root / "tests/test_calc.py").unlink()
        self.assertFalse(self.tools.call("run_tests", {})["success"])

    def test_timeout_cannot_validate(self):
        (self.root / "tests/test_calc.py").write_text("import time\ntime.sleep(10)\n")
        self.tools.timeout = 0.1
        result = self.tools.call("run_tests", {})
        self.assertTrue(result["timed_out"])
        self.assertFalse(result["success"])

    def test_source_snapshot_requires_clean_tree(self):
        (self.root / "calc.py").write_text("dirty")
        with self.assertRaises(PolicyError):
            snapshot(self.root, self.root / "copy")

    def test_ambiguous_replacement_rejected(self):
        self.prepare()
        (self.root / "calc.py").write_text("a - b\na - b\n")
        self.assertFalse(self.edit()["ok"])
