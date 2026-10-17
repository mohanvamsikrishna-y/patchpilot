"""One schema registry shared by the agent and MCP transport."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import sys
import uuid

from .runtime import PolicyError, allowed, command, git, safe_path, tree_hash


def schema(**fields):
    """Build the strict all-string input schema used by these small tools."""
    return {
        "type": "object",
        "properties": {k: {"type": "string"} for k in fields},
        "required": list(fields),
        "additionalProperties": False,
    }


SPECS = [
    (
        "search",
        "Search literal text in repository files. Use an empty query to list files.",
        schema(query=""),
    ),
    ("read_file", "Read a UTF-8 file before editing it.", schema(path="")),
    (
        "record_plan",
        "Save a brief implementation plan grounded in inspected code.",
        schema(plan=""),
    ),
    (
        "replace_text",
        "Replace one exact occurrence in an existing Python source file. Tests are protected.",
        schema(path="", old="", new="", operation_id=""),
    ),
    ("run_tests", "Execute the fixed unittest suite. No arbitrary shell commands.", schema()),
    (
        "finish",
        "Request review. Requires a nonempty patch and tests passing on the current tree.",
        schema(summary=""),
    ),
]


def definitions():
    """Expose one registry in the shape shared by MCP and model adapters."""
    return [
        {"name": name, "description": description, "inputSchema": inputs}
        for name, description, inputs in SPECS
    ]


def protected(name: str) -> bool:
    """Identify test and workflow paths that source-edit tools must not change."""
    p = Path(name)
    return (
        any(part in {"tests", "test", ".github"} for part in p.parts)
        or p.name.startswith("test_")
        or p.name.endswith("_test.py")
        or p.name in {"conftest.py", "setup.py"}
    )


class Toolset:
    """Own repository tool policy and validation state for one workspace.

    An ok result means the tool executed successfully. For run_tests, success
    separately describes whether validation passed. Providers must distinguish
    a completed test run with failures from a tool execution error.
    """

    def __init__(self, root: Path, runner: str = "local", timeout: float = 30):
        """Initialize per-workspace inspection, edit replay, and test-validation state."""
        self.root = root.resolve()
        self.runner = runner
        self.timeout = timeout
        self.operations: dict[str, tuple] = {}
        self.plan = ""
        self.summary = ""
        self.tests: list[dict] = []
        self.validated_tree: str | None = None
        self.read_paths: set[str] = set()

    def call(self, name: str, arguments: dict) -> dict:
        """Validate the exact tool arguments, dispatch the call, and return structured feedback."""
        spec = next((s for s in definitions() if s["name"] == name), None)
        if spec is None:
            return {"ok": False, "error": "unknown_tool", "message": name}
        # Reject unexpected fields as well as wrong types before dispatch.
        fields = spec["inputSchema"]["properties"]
        if (
            not isinstance(arguments, dict)
            or set(arguments) != set(fields)
            or any(not isinstance(v, str) for v in arguments.values())
            or any(len(v) > 32000 for v in arguments.values())
        ):
            return {
                "ok": False,
                "error": "invalid_arguments",
                "message": "Arguments must match the tool schema",
            }
        try:
            return {"ok": True, **getattr(self, name)(**arguments)}
        except (PolicyError, OSError, UnicodeError) as exc:
            return {"ok": False, "error": type(exc).__name__, "message": str(exc)}

    def search(self, query: str) -> dict:
        """Return bounded literal matches, or one match per nonempty file for an empty query."""
        matches = []
        for path in sorted(self.root.rglob("*")):
            relative = path.relative_to(self.root).as_posix()
            if not allowed(relative) or path.is_symlink() or not path.is_file():
                continue
            if path.stat().st_size > 100000:
                continue
            try:
                content = safe_path(self.root, relative).read_text()
            except (UnicodeError, PolicyError):
                continue
            for number, line in enumerate(content.splitlines(), 1):
                if query in line:
                    matches.append({"path": relative, "line": number, "text": line[:300]})
                    if not query:
                        break
                    if len(matches) >= 80:
                        return {"matches": matches, "truncated": True}
            if len(matches) >= 80:
                return {"matches": matches, "truncated": True}
        return {"matches": matches, "truncated": False}

    def read_file(self, path: str) -> dict:
        """Return bounded UTF-8 content and remember that the provider inspected this path."""
        target = safe_path(self.root, path)
        if target.stat().st_size > 32000:
            raise PolicyError("File exceeds 32 KB read limit")
        content = target.read_text()
        self.read_paths.add(path)
        return {"path": path, "content": content}

    def record_plan(self, plan: str) -> dict:
        """Record a nonempty implementation plan after at least one file inspection."""
        if not self.read_paths or not plan.strip():
            raise PolicyError("Inspect code before recording a nonempty plan")
        self.plan = plan
        return {"plan": plan}

    def replace_text(self, path: str, old: str, new: str, operation_id: str) -> dict:
        """Apply one unambiguous source edit after inspection and planning.

        Operation IDs bind arguments and the resulting file hash. A duplicate
        request can replay only while the saved resulting file still matches.
        Successful edits invalidate any earlier passing test result.
        """
        target = safe_path(self.root, path)
        if protected(path) or target.suffix != ".py":
            raise PolicyError("Only non-test Python source files can be edited")
        if path not in self.read_paths or not self.plan:
            raise PolicyError("Read the file and record a plan before editing")
        if not operation_id or not old or old == new:
            raise PolicyError("A unique operation ID and a nonempty change are required")
        # Replay identity includes the operation contents, not just its caller ID.
        signature = hashlib.sha256((path + "\0" + old + "\0" + new).encode()).hexdigest()
        if operation_id in self.operations:
            saved_signature, saved_hash, result = self.operations[operation_id]
            if saved_signature != signature:
                raise PolicyError("Operation ID reused with different arguments")
            if hashlib.sha256(target.read_bytes()).hexdigest() != saved_hash:
                raise PolicyError("File changed since the cached operation")
            return {**result, "replayed": True}
        content = target.read_text()
        if content.count(old) != 1:
            raise PolicyError("Old text must match exactly once")
        updated = content.replace(old, new, 1)
        if len(updated.encode()) > 32000:
            raise PolicyError("Updated file exceeds 32 KB limit")
        # Replace the whole file atomically after all edit checks have passed.
        temporary = target.with_name(target.name + ".patchpilot-tmp")
        temporary.write_text(updated)
        temporary.chmod(target.stat().st_mode & 0o777)
        temporary.replace(target)
        result = {"path": path, "changed": True, "replayed": False}
        self.operations[operation_id] = (
            signature,
            hashlib.sha256(target.read_bytes()).hexdigest(),
            result,
        )
        self.validated_tree = None
        return result

    def run_tests(self) -> dict:
        """Execute the fixed unittest suite locally or inside the Docker runner.

        Record counts and timings from unittest output. Validation requires a
        nonempty passing suite, no timeout, and an unchanged workspace hash.
        Local execution is for trusted code; output parsing is not attestation.
        """
        # Test evidence is valid only for the exact tree that produced it.
        before = tree_hash(self.root)
        environment = {k: v for k, v in os.environ.items() if k in {"PATH", "SYSTEMROOT", "LANG"}}
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        test_args = ["-B", "-m", "unittest", "discover", "-s", "tests", "-v"]
        container = "patchpilot-" + uuid.uuid4().hex[:12]
        # This boundary isolates the test subprocess, not the host controller.
        if self.runner == "docker":
            argv = [
                "docker",
                "run",
                "--rm",
                "--name",
                container,
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit=64",
                "--memory=256m",
                "--cpus=1",
                "--user=65534:65534",
                "--tmpfs",
                "/tmp:rw,size=32m",
                "--mount",
                f"type=bind,src={self.root},dst=/workspace,readonly",
                "-w",
                "/workspace",
                "patchpilot-runner:local",
                "python",
                *test_args,
            ]
        else:
            argv = [sys.executable, *test_args]
        try:
            result = command(argv, self.root, self.timeout, environment)
        finally:
            if self.runner == "docker":
                command(["docker", "rm", "-f", container], self.root, 10)
        output = result["output"]
        match = re.search(r"Ran (\d+) tests? in", output)
        total = int(match.group(1)) if match else 0
        counts = {
            k: int(v)
            for k, v in re.findall(
                r"(failures|errors|skipped|expected failures|unexpected successes)=(\d+)", output
            )
        }
        failed = sum(counts.get(k, 0) for k in ("failures", "errors", "unexpected successes"))
        skipped = counts.get("skipped", 0) + counts.get("expected failures", 0)
        passed = max(0, total - failed - skipped)
        # Exit zero alone is insufficient; an empty suite must never approve a patch.
        success = (
            result["exit_code"] == 0
            and total > 0
            and passed > 0
            and not result["timed_out"]
            and before == tree_hash(self.root)
        )
        result.update(
            {
                "success": success,
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "runner": self.runner,
                "tree_sha256": before,
                "pass_rate": passed / total if total else 0,
            }
        )
        self.tests.append(result)
        self.validated_tree = before if success else None
        return result

    def finish(self, summary: str) -> dict:
        """Request human review only for a nonempty patch tested against the current tree."""
        if not self.plan or not summary.strip():
            raise PolicyError("Plan and summary are required")
        if self.validated_tree is None or self.validated_tree != tree_hash(self.root):
            raise PolicyError("Run passing tests against the current tree before requesting review")
        if not git(self.root, "diff", "--no-ext-diff", "--no-textconv"):
            raise PolicyError("No patch to review")
        self.summary = summary
        return {"status": "awaiting_review", "summary": summary}
