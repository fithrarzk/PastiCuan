import subprocess
import unittest
import os
from unittest.mock import patch

from operations.production_db_lock import (
    LOCK_KEY,
    main,
    run_with_production_db_lock,
)


class FakeCursor:
    def __init__(self, acquisitions):
        self.acquisitions = iter(acquisitions)
        self.calls = []
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))
        if "try_advisory" in statement:
            self._row = (next(self.acquisitions),)

    def fetchone(self):
        return self._row


class FakeConnection:
    def __init__(self, acquisitions=(True,)):
        self.autocommit = False
        self.closed = False
        self.cursor_value = FakeCursor(acquisitions)

    def cursor(self):
        return self.cursor_value

    def close(self):
        self.closed = True


class UnlockFailingCursor(FakeCursor):
    def execute(self, statement, parameters):
        if "advisory_unlock" in statement:
            raise RuntimeError("unlock failed")
        super().execute(statement, parameters)


class UnlockFailingConnection(FakeConnection):
    def __init__(self):
        super().__init__()
        self.cursor_value = UnlockFailingCursor((True,))


class ProductionDatabaseLockTests(unittest.TestCase):
    def test_exclusive_lock_runs_child_and_always_releases_session(self):
        connection = FakeConnection()
        commands = []

        def runner(command, check=False):
            commands.append((command, check))
            return subprocess.CompletedProcess(command, 7)

        code = run_with_production_db_lock(
            ["python", "-m", "operations.research_cli", "run-daily-research"],
            mode="exclusive",
            wait_seconds=0,
            connect=lambda: connection,
            runner=runner,
        )

        self.assertEqual(code, 7)
        self.assertTrue(connection.autocommit)
        self.assertEqual(
            commands,
            [
                (
                    [
                        "python",
                        "-m",
                        "operations.research_cli",
                        "run-daily-research",
                    ],
                    False,
                )
            ],
        )
        self.assertEqual(
            connection.cursor_value.calls,
            [
                ("SELECT pg_try_advisory_lock(%s, %s)", LOCK_KEY),
                ("SELECT pg_advisory_unlock(%s, %s)", LOCK_KEY),
            ],
        )
        self.assertTrue(connection.closed)

    def test_shared_lock_uses_matching_shared_acquire_and_release(self):
        connection = FakeConnection()

        code = run_with_production_db_lock(
            ["import-one-filing-shard"],
            mode="shared",
            wait_seconds=0,
            connect=lambda: connection,
            runner=lambda command, check=False: subprocess.CompletedProcess(command, 0),
        )

        self.assertEqual(code, 0)
        self.assertEqual(
            connection.cursor_value.calls,
            [
                ("SELECT pg_try_advisory_lock_shared(%s, %s)", LOCK_KEY),
                ("SELECT pg_advisory_unlock_shared(%s, %s)", LOCK_KEY),
            ],
        )

    def test_unavailable_lock_times_out_without_running_child(self):
        connection = FakeConnection(acquisitions=(False,))
        commands = []
        messages = []

        code = run_with_production_db_lock(
            ["must-not-run"],
            mode="exclusive",
            wait_seconds=0,
            connect=lambda: connection,
            runner=lambda command, check=False: commands.append(command),
            stderr=messages.append,
        )

        self.assertEqual(code, 75)
        self.assertEqual(commands, [])
        self.assertEqual(messages, ["production database lock unavailable\n"])
        self.assertTrue(connection.closed)

    def test_lock_waits_between_try_attempts_until_acquired(self):
        connection = FakeConnection(acquisitions=(False, True))
        pauses = []
        ticks = iter((0.0, 0.0))

        code = run_with_production_db_lock(
            ["eventually-runs"],
            mode="exclusive",
            wait_seconds=2,
            connect=lambda: connection,
            runner=lambda command, check=False: subprocess.CompletedProcess(command, 0),
            poll_seconds=0.5,
            clock=lambda: next(ticks),
            sleep=pauses.append,
        )

        self.assertEqual(code, 0)
        self.assertEqual(pauses, [0.5])
        self.assertEqual(len(connection.cursor_value.calls), 3)

    def test_cli_passes_mode_wait_and_command_to_lock_runner(self):
        with patch(
            "operations.production_db_lock.run_with_production_db_lock",
            return_value=0,
        ) as run:
            code = main(
                [
                    "--mode",
                    "shared",
                    "--wait-seconds",
                    "12",
                    "--",
                    "python",
                    "-m",
                    "operations.research_cli",
                    "ingest-idx-xbrl",
                ]
            )

        self.assertEqual(code, 0)
        run.assert_called_once_with(
            [
                "python",
                "-m",
                "operations.research_cli",
                "ingest-idx-xbrl",
            ],
            mode="shared",
            wait_seconds=12.0,
        )

    def test_lock_rejects_unbounded_wait_configuration(self):
        with self.assertRaisesRegex(ValueError, "bounded"):
            run_with_production_db_lock(
                ["child"], mode="exclusive", wait_seconds=float("inf")
            )

    def test_child_exception_still_releases_the_lock(self):
        connection = FakeConnection()

        def runner(command, check=False):
            raise OSError("child failed")

        with self.assertRaises(OSError):
            run_with_production_db_lock(
                ["child"],
                mode="exclusive",
                wait_seconds=0,
                connect=lambda: connection,
                runner=runner,
            )

        self.assertEqual(
            connection.cursor_value.calls,
            [
                ("SELECT pg_try_advisory_lock(%s, %s)", LOCK_KEY),
                ("SELECT pg_advisory_unlock(%s, %s)", LOCK_KEY),
            ],
        )
        self.assertTrue(connection.closed)

    def test_unlock_error_still_closes_the_session(self):
        connection = UnlockFailingConnection()

        with self.assertRaisesRegex(RuntimeError, "unlock failed"):
            run_with_production_db_lock(
                ["child"],
                mode="exclusive",
                wait_seconds=0,
                connect=lambda: connection,
                runner=lambda command, check=False: subprocess.CompletedProcess(
                    command, 0
                ),
            )

        self.assertTrue(connection.closed)

    @unittest.skipUnless(
        os.getenv("PASTICUAN_TEST_DATABASE_URL"),
        "disposable PostgreSQL required",
    )
    def test_real_shared_holders_exclude_an_exclusive_holder(self):
        import psycopg

        url = os.environ["PASTICUAN_TEST_DATABASE_URL"]
        first = psycopg.connect(url)
        second = psycopg.connect(url)
        probe = psycopg.connect(url)
        try:
            first.autocommit = True
            second.autocommit = True
            probe.autocommit = True
            events = []
            with first.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock_shared(%s, %s)", LOCK_KEY)
                self.assertTrue(cursor.fetchone()[0])

            def probe_runner(command, check=False):
                with probe.cursor() as cursor:
                    cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", LOCK_KEY)
                    events.append(cursor.fetchone()[0])
                return subprocess.CompletedProcess(command, 0)

            def second_runner(command, check=False):
                code = run_with_production_db_lock(
                    ["probe"],
                    mode="exclusive",
                    wait_seconds=0,
                    connect=lambda: probe,
                    runner=probe_runner,
                )
                return subprocess.CompletedProcess(command, code)

            code = run_with_production_db_lock(
                ["second"],
                mode="shared",
                wait_seconds=0,
                connect=lambda: second,
                runner=second_runner,
            )
            self.assertEqual(code, 75)
            self.assertEqual(events, [False])
        finally:
            first.close()
            second.close()
            probe.close()


if __name__ == "__main__":
    unittest.main()
