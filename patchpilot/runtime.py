"""Subprocess limits, repository boundaries, and a disposable Git workspace."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


class PolicyError(ValueError):
    pass


IGNORED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".ssh", ".aws"}


def allowed(path: str) -> bool:
    p = Path(path)
    return (not p.is_absolute() and ".." not in p.parts
            and not any(part in IGNORED for part in p.parts)
            and not any(part.startswith(".env") for part in p.parts)
            and p.suffix not in {".pem", ".key", ".p12"})


def safe_path(root: Path, relative: str) -> Path:
    if not relative or not allowed(relative):
        raise PolicyError("Path is outside the permitted repository surface")
    p = root / relative
    if any(part.is_symlink() for part in [p, *p.parents] if part != root.parent):
        raise PolicyError("Symlink paths are not supported")
    if not p.resolve().is_relative_to(root.resolve()):
        raise PolicyError("Path escapes workspace")
    return p


def command(argv: list[str], cwd: Path, timeout: float = 30,
            env: dict | None = None) -> dict:
    """No shell. Spill output to disk to avoid unbounded in-memory capture."""
    started = time.monotonic()
    with tempfile.TemporaryFile() as output:
        proc = subprocess.Popen(argv, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                                start_new_session=True, env=env)
        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        size = output.tell()
        output.seek(max(0, size - 24000))
        text = output.read().decode("utf-8", errors="replace")
    return {"exit_code": proc.returncode, "output": text, "timed_out": timed_out,
            "truncated": size > 24000, "duration_seconds": round(time.monotonic() - started, 3)}


def git(root: Path, *args: str) -> str:
    result = command(["git", "-c", "core.hooksPath=/dev/null", *args], root)
    if result["exit_code"]:
        raise PolicyError(result["output"].strip())
    if result["truncated"]:
        raise PolicyError("Git output exceeds prototype limit; refusing partial data")
    return result["output"].strip()


def init_repository(root: Path) -> None:
    git(root, "init", "-b", "main")
    git(root, "add", ".")
    git(root, "-c", "user.name=PatchPilot", "-c", "user.email=patchpilot@example.invalid",
        "commit", "-m", "Capture task baseline")


def snapshot(source: Path, destination: Path) -> str:
    """Only clean, tracked regular files. Never copy Git credentials or hooks."""
    source = source.resolve()
    if git(source, "status", "--porcelain"):
        raise PolicyError("Source must be clean. Commit or stash changes before running.")
    base = git(source, "rev-parse", "HEAD")
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=source).decode().split("\0")
    destination.mkdir(parents=True)
    for name in filter(None, names):
        if not allowed(name):
            continue
        original = safe_path(source, name)
        if not original.is_file():
            raise PolicyError("Submodules and non-regular files are unsupported")
        if original.stat().st_size > 1_000_000:
            raise PolicyError("Files over 1 MB are unsupported in this prototype")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original.read_bytes())
        target.chmod(original.stat().st_mode & 0o777)
    init_repository(destination)
    return base


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        name = p.relative_to(root).as_posix()
        if p.is_file() and allowed(name):
            digest.update(name.encode() + b"\0" + p.read_bytes() + b"\0")
    return digest.hexdigest()
