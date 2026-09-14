"""Run one production database command under the shared orchestration lock."""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from typing import Any

# Two explicit int32 keys spell a stable PastiCuan-owned lock namespace.
LOCK_KEY = (0x50415354, 0x49435541)
LOCK_UNAVAILABLE_EXIT = 75
DEFAULT_WAIT_SECONDS = 900.0
MAX_WAIT_SECONDS = 1800.0


def _connect_writer():
    from storage.database import connect_from_env

    return connect_from_env(writer=True)


def run_with_production_db_lock(
    command: Sequence[str],
    *,
    mode: str,
    wait_seconds: float,
    connect: Callable[[], Any] | None = None,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
    poll_seconds: float = 1.0,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    stderr: Callable[[str], Any] | None = None,
) -> int:
    """Run ``command`` while this session owns the production writer lock."""
    if mode not in {"shared", "exclusive"}:
        raise ValueError("Lock mode must be 'shared' or 'exclusive'.")
    if (
        not math.isfinite(wait_seconds)
        or not 0 <= wait_seconds <= MAX_WAIT_SECONDS
        or not math.isfinite(poll_seconds)
        or poll_seconds <= 0
    ):
        raise ValueError("Lock wait must be bounded and polling positive.")
    monotonic = clock or time.monotonic
    pause = sleep or time.sleep
    write_stderr = stderr or sys.stderr.write
    connection = (connect or _connect_writer)()
    acquired = False
    deadline = monotonic() + wait_seconds
    try:
        connection.autocommit = True
        acquire_function = (
            "pg_try_advisory_lock_shared"
            if mode == "shared"
            else "pg_try_advisory_lock"
        )
        while not acquired:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT {acquire_function}(%s, %s)", LOCK_KEY)
                acquired = bool(cursor.fetchone()[0])
            if acquired:
                break
            remaining = deadline - monotonic()
            if remaining <= 0:
                write_stderr("production database lock unavailable\n")
                return LOCK_UNAVAILABLE_EXIT
            pause(min(poll_seconds, remaining))
        if not acquired:
            write_stderr("production database lock unavailable\n")
            return LOCK_UNAVAILABLE_EXIT
        result = (runner or subprocess.run)(list(command), check=False)
        return int(result.returncode)
    finally:
        try:
            if acquired:
                with connection.cursor() as cursor:
                    unlock_function = (
                        "pg_advisory_unlock_shared"
                        if mode == "shared"
                        else "pg_advisory_unlock"
                    )
                    cursor.execute(f"SELECT {unlock_function}(%s, %s)", LOCK_KEY)
        finally:
            connection.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("shared", "exclusive"), required=True)
    parser.add_argument("--wait-seconds", type=float, default=DEFAULT_WAIT_SECONDS)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    return run_with_production_db_lock(
        args.command,
        mode=args.mode,
        wait_seconds=args.wait_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
