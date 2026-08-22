import json
import math
from contextlib import redirect_stdout
from decimal import Decimal
from io import StringIO
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from analysis.contracts import strict_json_dumps
from operations.job_outcomes import EXIT_CODES, PERSISTED_STATUSES, EvidenceUnavailable, Outcome
from operations.research_cli import _report_write_failure, build_snapshot, main
from storage.repository import SnapshotRepository


class OperationalOutcomeContractTests(unittest.TestCase):
    def test_outcomes_have_stable_exit_and_persisted_contracts(self):
        expected = {
            Outcome.SUCCEEDED: (0, "SUCCEEDED"),
            Outcome.NOOP: (0, "SUCCEEDED"),
            Outcome.WAITING: (10, "DEGRADED"),
            Outcome.UNAVAILABLE: (20, "DEGRADED"),
            Outcome.POLICY_GATE: (30, "FAILED"),
            Outcome.INFRASTRUCTURE: (40, "FAILED"),
        }
        self.assertEqual(
            {kind: (EXIT_CODES[kind], PERSISTED_STATUSES[kind].value) for kind in Outcome},
            expected,
        )

    def test_strict_encoder_turns_nested_python_and_numpy_nonfinite_values_null(self):
        payload = {"rows": [{"nan": math.nan, "positive": np.inf, "negative": -np.inf,
                              "array": np.array([math.nan, np.inf])}]}
        encoded = strict_json_dumps(payload)
        self.assertEqual(json.loads(encoded), {
            "rows": [{"nan": None, "positive": None, "negative": None,
                      "array": [None, None]}]
        })
        self.assertNotIn("NaN", encoded)
        self.assertNotIn("Infinity", encoded)

    def test_strict_encoder_handles_pandas_and_decimal_nonfinite_values(self):
        payload = {
            "missing": [pd.NA, pd.NaT],
            "decimal": [Decimal("NaN"), Decimal("Infinity"), Decimal("1.25")],
        }
        encoded = strict_json_dumps(payload, allow_nan=True)
        self.assertEqual(json.loads(encoded), {
            "missing": [None, None], "decimal": [None, None, 1.25]
        })

    def test_strict_encoder_handles_longdouble_and_complex_nonfinite_values(self):
        payload = {
            "longdouble": np.longdouble("inf"),
            "complex": [complex(float("nan"), 1), np.clongdouble("inf+1j")],
        }
        encoded = strict_json_dumps(payload)
        decoded = json.loads(encoded)
        self.assertIsNone(decoded["longdouble"])
        self.assertEqual(decoded["complex"], [None, None])


class MigrationPreflightTests(unittest.TestCase):
    def test_ledger_absence_is_distinct_from_missing_versions(self):
        class Cursor:
            def execute(self, sql):
                self.sql = sql

            def fetchone(self):
                return (True,) if "schema_privilege" in self.sql else (None,)

            def fetchall(self):
                return []

        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def cursor(self): return CursorContext()

        class CursorContext(Cursor):
            def __enter__(self): return self
            def __exit__(self, *args): pass

        result = SnapshotRepository(lambda: Connection()).preflight_schema_migrations(["001"])
        self.assertEqual(result["code"], "LEDGER_ABSENT")
        self.assertFalse(result["ok"])

    def test_privilege_denial_does_not_expose_exception_text(self):
        class Denied(Exception):
            pgcode = "42501"

        class Cursor:
            def execute(self, sql):
                self.sql = sql
                if "schema_privilege" in sql or "to_regclass" in sql:
                    return
                raise Denied("sensitive-marker")

            def fetchone(self):
                return (True,) if "schema_privilege" in self.sql else ("schema_migrations",)
            def fetchall(self): return []

        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def cursor(self): return CursorContext()

        class CursorContext(Cursor):
            def __enter__(self): return self
            def __exit__(self, *args): pass

        result = SnapshotRepository(lambda: Connection()).preflight_schema_migrations(["001"])
        self.assertEqual(result["code"], "LEDGER_TABLE_PRIVILEGE_DENIED")
        self.assertNotIn("sensitive-marker", repr(result))

    def test_required_version_absence_is_distinct(self):
        class Cursor:
            def execute(self, sql):
                self.sql = sql
            def fetchone(self):
                if "schema_privilege" in self.sql:
                    return (True,)
                if "to_regclass" in self.sql:
                    return ("schema_migrations",)
                return (True,)
            def fetchall(self):
                return [("001",)]

        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def cursor(self): return CursorContext()

        class CursorContext(Cursor):
            def __enter__(self): return self
            def __exit__(self, *args): pass

        result = SnapshotRepository(lambda: Connection()).preflight_schema_migrations(["001", "002"])
        self.assertEqual(result, {
            "ok": False, "code": "REQUIRED_MIGRATION_MISSING", "missing_versions": ["002"]
        })

    def test_python_timeout_is_a_stable_ledger_timeout(self):
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def cursor(self): raise TimeoutError()

        result = SnapshotRepository(lambda: Connection()).preflight_schema_migrations(["001"])
        self.assertEqual(result["code"], "LEDGER_TIMEOUT")


class ReportFailureTests(unittest.TestCase):
    def test_report_write_failure_emits_redacted_infrastructure_without_retry(self):
        recorded = []
        stream = StringIO()
        with redirect_stdout(stream):
            result = _report_write_failure(
                {"started_at": "2026-08-22T00:00:00+00:00", "stages": {"scan": {}}},
                type("Repository", (), {"record_research_job": recorded.append})(),
                {"id": "run", "job_type": "DAILY_RESEARCH", "started_at": "now"},
            )
        self.assertEqual(result["outcome"]["exit_code"], 40)
        self.assertEqual(result["outcome"]["code"], "REPORT_WRITE_FAILED")
        self.assertEqual(len(recorded), 1)
        self.assertNotIn("/", stream.getvalue())

    def test_cli_does_not_duplicate_already_emitted_report_failure(self):
        stream = StringIO()
        result = {"status": "FAILED", "_stdout_emitted": True,
                  "outcome": {"exit_code": 40}, "stages": {}}
        def failed_run(*args, **kwargs):
            print('{"outcome":{"exit_code":40}}')
            return result
        with patch("operations.research_cli.run_daily_research", side_effect=failed_run), \
                redirect_stdout(stream):
            code = main(["run-daily-research", "--output", "unused.json"])
        self.assertEqual(code, 40)
        self.assertEqual(len(stream.getvalue().splitlines()), 1)


class SnapshotEvidenceTests(unittest.TestCase):
    def test_computed_unavailable_snapshot_raises_typed_evidence_failure(self):
        with TemporaryDirectory() as root:
            input_path = Path(root) / "inputs.csv"
            input_path.write_text("ticker,close\nTEST,1\n")
            with patch("operations.research_cli.compute_cross_sectional_factors",
                       return_value={"status": "UNAVAILABLE", "reason": "not used"}):
                with self.assertRaises(EvidenceUnavailable):
                    build_snapshot(str(input_path), str(Path(root) / "snapshot.json"),
                                   "2026-08-22T00:00:00+00:00", "test-model")

    def test_build_snapshot_cli_maps_typed_evidence_failure_to_exit20(self):
        with patch("operations.research_cli.build_snapshot", side_effect=EvidenceUnavailable()), \
                redirect_stdout(StringIO()) as stream:
            code = main(["build-snapshot", "--input", "inputs.csv", "--output", "snapshot.json",
                         "--effective-at", "2026-08-22T00:00:00+00:00"])
        self.assertEqual(code, 20)
        self.assertEqual(len(stream.getvalue().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
