"""Inspect and apply a reviewed patch to a clean local checkout."""
import hashlib
import json
from pathlib import Path

from .runtime import PolicyError, git


def load_review(folder: Path) -> tuple[dict, str]:
    result = json.loads((folder / "run.json").read_text())
    patch_bytes = (folder / "patch.diff").read_bytes()
    if result["status"] != "awaiting_review" or not patch_bytes:
        raise PolicyError("This run has no validated patch to apply")
    if hashlib.sha256(patch_bytes).hexdigest() != result["patch_sha256"]:
        raise PolicyError("Patch changed since validation; rerun before applying")
    return result, patch_bytes.decode()


def apply_plan(folder: Path, target: Path) -> dict:
    result, _ = load_review(folder)
    target = target.resolve()
    if git(target, "rev-parse", "--show-toplevel") != str(target):
        raise PolicyError("Target must be the repository root")
    if git(target, "status", "--porcelain"):
        raise PolicyError("Target has uncommitted changes")
    if git(target, "rev-parse", "HEAD") != result["base_commit"]:
        raise PolicyError("Target HEAD differs from the tested source commit")
    git(target, "apply", "--check", str((folder / "patch.diff").resolve()))
    plan = {"target": str(target), "base_commit": result["base_commit"],
            "patch_sha256": result["patch_sha256"], "run_id": result["run_id"]}
    plan["approval_sha256"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    return plan


def apply_patch(folder: Path, target: Path, approval: str) -> dict:
    plan = apply_plan(folder, target)
    if approval != plan["approval_sha256"]:
        raise PolicyError("Approval must match the exact target and patch plan")
    git(target.resolve(), "apply", str((folder / "patch.diff").resolve()))
    receipt = {**plan, "status": "applied", "committed": False}
    (folder / "apply-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt
