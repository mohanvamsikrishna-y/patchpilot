"""Readiness checks do not print credentials or invoke a model."""
import os
from pathlib import Path
import shutil
import sys

from .runtime import command


def inspect_environment():
    checks = [{"name": "Python", "ready": sys.version_info >= (3, 10), "detail": sys.version.split()[0]},
              {"name": "Git", "ready": bool(shutil.which("git")), "detail": "Required for every run"},
              {"name": "OpenAI API key", "ready": bool(os.getenv("OPENAI_API_KEY")),
               "detail": "Optional for --provider openai; value is never displayed"}]
    for binary, args, label in [("codex", ["login", "status"], "Codex sign-in"),
                                ("docker", ["image", "inspect", "patchpilot-runner:local"], "Docker runner image"),
                                ("gh", ["auth", "status"], "GitHub sign-in")]:
        found = shutil.which(binary)
        result = command([binary, *args], Path.cwd(), timeout=10) if found else None
        ready = bool(result and result["exit_code"] == 0)
        checks.append({"name": label, "ready": ready,
                       "detail": "Ready" if ready else ("Not installed" if not found else "Not ready; configure before use")})
    return checks
