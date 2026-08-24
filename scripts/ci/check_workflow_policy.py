"""Fail closed on unsafe or non-reproducible GitHub workflow policy."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

import yaml


SHA_ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}(?:\s+#.*)?$")
REQUIRED_JOBS = {
    "test",
    "unit",
    "quality",
    "workflow-policy",
    "migration",
    "container-smoke",
    "manifest-validate",
    "security",
}
SAFE_RESEARCH_PUSH_IGNORES = {
    ".agents/**",
    ".github/workflows/ci.yml",
    ".github/workflows/test.yml",
    ".github/workflows/validate-branch.yml",
    "AGENTS.md",
    "CONTEXT.md",
    "DEPLOY_FREE.md",
    "README.md",
    "docs/**",
    "requirements-ci.txt",
    "scripts/ci/**",
    "tests/**",
}
IDX_JOB_PERMISSIONS = {
    "discover": {"contents": "write", "pull-requests": "write", "actions": "write"},
    "import": {"contents": "read", "actions": "write"},
}


def _workflow_data(path: Path) -> dict:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: workflow is not a mapping")
    return data


def validate_workflow(path: Path, *, require_required_jobs: bool = False) -> list[str]:
    errors: list[str] = []
    try:
        workflow = _workflow_data(path)
    except Exception as exc:
        return [f"{path}: YAML parse failed: {exc}"]
    if not workflow.get("concurrency"):
        errors.append(f"{path}: concurrency is required")
    if "permissions" not in workflow:
        errors.append(f"{path}: explicit workflow permissions are required")
    permissions = workflow.get("permissions", {})
    if permissions != "read-all" and any(
        value == "write" for value in (permissions or {}).values()
    ):
        errors.append(f"{path}: workflow-level permissions must not grant write")
    jobs = workflow.get("jobs") or {}
    if require_required_jobs and REQUIRED_JOBS - set(jobs):
        errors.append(
            f"{path}: missing jobs: {', '.join(sorted(REQUIRED_JOBS - set(jobs)))}"
        )
    if require_required_jobs:
        for required_name in sorted(REQUIRED_JOBS & set(jobs)):
            if jobs[required_name].get("name") != required_name:
                errors.append(
                    f"{path}: job {required_name} must display name {required_name!r}"
                )
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            errors.append(f"{path}: job {job_name} is not a mapping")
            continue
        if not job.get("timeout-minutes"):
            errors.append(f"{path}: job {job_name} has no timeout-minutes")
        job_permissions = job.get("permissions", {})
        if path.name == "idx-filings.yml" and job_name in IDX_JOB_PERMISSIONS:
            expected = IDX_JOB_PERMISSIONS[job_name]
            if job_permissions != expected:
                errors.append(
                    f"{path}: job {job_name} permissions must be exactly {expected}"
                )
        elif any(value == "write" for value in (job_permissions or {}).values()):
            errors.append(f"{path}: job {job_name} grants write permission")
        for service_name, service in (job.get("services") or {}).items():
            image = service.get("image", "") if isinstance(service, dict) else ""
            if "@sha256:" not in str(image):
                errors.append(
                    f"{path}: service image {service_name} is not immutable: {image}"
                )
        for step in job.get("steps", []):
            action = step.get("uses") if isinstance(step, dict) else None
            if action and not SHA_ACTION.match(str(action)):
                errors.append(f"{path}: action is not immutable: {action}")
    trigger = workflow.get("on", workflow.get(True, {}))
    trigger = trigger if isinstance(trigger, dict) else {}
    if path.name == "ci.yml":
        if "pull_request" not in trigger:
            errors.append(f"{path}: pull_request trigger is required")
    if path.name == "ci.yml" and "push" in trigger:
        push = trigger["push"] or {}
        branches = push.get("branches", []) if isinstance(push, dict) else []
        if branches != ["main"]:
            errors.append(f"{path}: push trigger must be restricted to main")
    if path.name == "research-daily.yml":
        push = trigger.get("push") or {}
        branches = push.get("branches", []) if isinstance(push, dict) else []
        ignored = set(push.get("paths-ignore", [])) if isinstance(push, dict) else set()
        if branches != ["main"]:
            errors.append(f"{path}: research push must be restricted to main")
        if ignored != SAFE_RESEARCH_PUSH_IGNORES:
            errors.append(
                f"{path}: research push must use the exact safe paths-ignore set"
            )
    if path.name == "validate-branch.yml":
        if set(trigger) != {"workflow_dispatch"}:
            errors.append(f"{path}: generated validation must be dispatch-only")
        text = path.read_text()
        for forbidden in ("discover-idx-xbrl", "gh pr", "gh workflow run"):
            if forbidden in text:
                errors.append(
                    f"{path}: generated validation contains recursion command: {forbidden}"
                )
    return errors


def changed_workflows(base_ref: str) -> list[Path]:
    output = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD", "--", ".github/workflows"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return [Path(name) for name in output if name.endswith((".yml", ".yaml"))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--required-jobs", action="store_true")
    parser.add_argument(
        "--base-ref", help="include every workflow changed relative to this ref"
    )
    args = parser.parse_args()
    # The PR policy owns the primary and generated required-check producers.
    # Operational workflows are reviewed by their own task cards and can be
    # passed explicitly when their policy is being changed.
    paths = args.paths or [
        Path(".github/workflows/ci.yml"),
        Path(".github/workflows/validate-branch.yml"),
    ]
    required_paths = (
        set(paths)
        if args.paths
        else {
            Path(".github/workflows/ci.yml"),
            Path(".github/workflows/validate-branch.yml"),
        }
    )
    if args.base_ref:
        paths = list(dict.fromkeys(paths + changed_workflows(args.base_ref)))
    errors = [
        error
        for path in paths
        for error in validate_workflow(
            path, require_required_jobs=args.required_jobs and path in required_paths
        )
    ]
    if errors:
        print("\n".join(errors))
        return 1
    print(f"workflow policy passed for {len(paths)} workflow(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
