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
    "data/idx_filing_manifest.json",
    "data/source_manifest.json",
}
IDX_JOB_PERMISSIONS = {
    "discover": {"contents": "write", "pull-requests": "write", "actions": "write"},
    "prepare-import": {"contents": "read"},
    "import-shards": {"contents": "read"},
    "aggregate": {"contents": "read", "actions": "write"},
}
PRODUCTION_WRITER_WORKFLOWS = {
    "idx-filings.yml",
    "research-daily.yml",
    "research-validation.yml",
    "backup.yml",
}
PRODUCTION_DATABASE_COMMANDS = {
    "ingest-manifest": "exclusive",
    "ingest-idx-xbrl": "exclusive",
    "discover-idx-xbrl": "exclusive",
    "run-daily-research": "exclusive",
    "rebuild-monthly-panel": "exclusive",
    "validate-quant": "exclusive",
    "backup": "exclusive",
}


def _workflow_data(path: Path) -> dict:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: workflow is not a mapping")
    return data


def _validate_production_writer_lock(path: Path, workflow: dict) -> list[str]:
    """Require every production database command to use the shared lock CLI."""
    if path.name not in PRODUCTION_WRITER_WORKFLOWS:
        return []
    text = path.read_text()
    is_repository_workflow = (
        path.parent.name == "workflows" and path.parent.parent.name == ".github"
    )
    if not is_repository_workflow and "SUPABASE_WRITER_DATABASE_URL" not in text:
        return []
    errors: list[str] = []
    if "SUPABASE_WRITER_DATABASE_URL" not in text:
        errors.append(f"{path}: production writer URL is required")
    if "operations.production_db_lock" not in text:
        errors.append(f"{path}: production database lock wrapper is required")
    for job_name, job in (workflow.get("jobs") or {}).items():
        for step in job.get("steps", []):
            run = step.get("run", "") if isinstance(step, dict) else ""
            if not isinstance(run, str):
                continue
            for command, mode in PRODUCTION_DATABASE_COMMANDS.items():
                if f"operations.research_cli {command}" not in run:
                    continue
                expected_mode = (
                    "shared"
                    if command == "ingest-idx-xbrl" and job_name == "import-shards"
                    else mode
                )
                if "operations.production_db_lock" not in run:
                    errors.append(
                        f"{path}: {job_name}/{step.get('name', 'run')} "
                        f"wraps {command} without production_db_lock"
                    )
                if f"production_db_lock --mode {expected_mode}" not in run:
                    errors.append(
                        f"{path}: {job_name}/{step.get('name', 'run')} "
                        f"must use {expected_mode} production_db_lock mode for {command}"
                    )
    if path.name == "idx-filings.yml":
        jobs = workflow.get("jobs") or {}
        discover_steps = jobs.get("discover", {}).get("steps", [])
        discover_names = [step.get("name") for step in discover_steps]
        discover_validation_names = {
            "Validate reviewed source manifest before discovery",
            "Validate reviewed Filing manifest before source ingestion",
        }
        missing_discover_validation = discover_validation_names - set(discover_names)
        if missing_discover_validation:
            errors.append(f"{path}: discover must validate both checked-in manifests")
        discover_validation_text = "\n".join(
            step.get("run", "")
            for step in discover_steps
            if step.get("name") in discover_validation_names
        )
        if "data/source_manifest.json --kind source" not in discover_validation_text:
            errors.append(f"{path}: discover source manifest validation is required")
        if (
            "data/idx_filing_manifest.json --kind filing"
            not in discover_validation_text
        ):
            errors.append(f"{path}: discover Filing manifest validation is required")
        prepare_steps = jobs.get("prepare-import", {}).get("steps", [])
        names = [step.get("name") for step in prepare_steps]
        validation_index = (
            names.index("Validate reviewed manifests before import")
            if "Validate reviewed manifests before import" in names
            else -1
        )
        ingest_index = (
            names.index("Import reviewed source manifest")
            if "Import reviewed source manifest" in names
            else -1
        )
        if validation_index < 0 or ingest_index < 0 or validation_index > ingest_index:
            errors.append(f"{path}: manifest validation must precede import")
        discover_ingest_index = (
            discover_names.index("Import reviewed source manifest")
            if "Import reviewed source manifest" in discover_names
            else -1
        )
        for validation_name in discover_validation_names:
            validation_index = (
                discover_names.index(validation_name)
                if validation_name in discover_names
                else -1
            )
            if (
                validation_index < 0
                or discover_ingest_index < 0
                or validation_index > discover_ingest_index
            ):
                errors.append(
                    f"{path}: discover manifest validation must precede source import"
                )
        shard_runs = "\n".join(
            step.get("run", "")
            for step in jobs.get("import-shards", {}).get("steps", [])
        )
        if "production_db_lock --mode shared" not in shard_runs:
            errors.append(f"{path}: import shards must use shared production_db_lock")
        aggregate = jobs.get("aggregate", {})
        readiness = next(
            (
                step
                for step in aggregate.get("steps", [])
                if step.get("name") == "Verify durable import readiness"
            ),
            None,
        )
        if readiness is None:
            errors.append(f"{path}: durable import readiness step is required")
        else:
            readiness_run = readiness.get("run", "")
            if (
                "production_db_lock --mode exclusive" not in readiness_run
                or "operations.research_cli ingest-idx-xbrl" not in readiness_run
                or "--aggregate-only" not in readiness_run
            ):
                errors.append(
                    f"{path}: durable readiness must run aggregate-only under an exclusive lock"
                )
            if readiness.get("id") != "progress":
                errors.append(f"{path}: durable readiness must expose id progress")
        needs = set(aggregate.get("needs", []))
        if not {"prepare-import", "import-shards"}.issubset(needs):
            errors.append(
                f"{path}: aggregate readiness must depend on prepare-import and import-shards"
            )
        refresh_dispatches = sum(
            step.get("run", "").count("gh workflow run research-daily.yml")
            for step in aggregate.get("steps", [])
        )
        if refresh_dispatches != 1:
            errors.append(
                f"{path}: exactly one guarded research refresh dispatch is required"
            )
        refresh_steps = [
            step
            for step in aggregate.get("steps", [])
            if "gh workflow run research-daily.yml" in step.get("run", "")
        ]
        if len(refresh_steps) != 1 or refresh_steps[0].get("if") != (
            "needs.import-shards.result == 'success' && "
            "steps.progress.outcome == 'success'"
        ):
            errors.append(
                f"{path}: research refresh dispatch must be guarded by readiness"
            )
    if path.name == "research-daily.yml":
        trigger = workflow.get("on", workflow.get(True, {}))
        ignored = set((trigger.get("push") or {}).get("paths-ignore", []))
        if {"data/idx_filing_manifest.json", "data/source_manifest.json"} - ignored:
            errors.append(f"{path}: manifest pushes must not launch research directly")
    return errors


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
    errors.extend(_validate_production_writer_lock(path, workflow))
    return errors


def changed_workflows(base_ref: str, *, repository: Path = Path(".")) -> list[Path]:
    def names(diff_filter: str) -> list[str]:
        return subprocess.run(
            [
                "git",
                "diff",
                "--name-only",
                f"--diff-filter={diff_filter}",
                f"{base_ref}...HEAD",
                "--",
                ".github/workflows",
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=repository,
        ).stdout.splitlines()

    changed = names("ACMR")
    deleted = [name for name in names("D") if name != ".github/workflows/test.yml"]
    return [
        Path(name) for name in changed + deleted if name.endswith((".yml", ".yaml"))
    ]


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
