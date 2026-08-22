import unittest

from storage.repository import SnapshotRepository


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = []
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exited = True

    def execute(self, query):
        self.executed.append(query)

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = _FakeCursor(rows)
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exited = True

    def cursor(self):
        return self.cursor_instance


class AppliedSchemaMigrationsCompatibilityTests(unittest.TestCase):
    def _repository(self, rows):
        connection = _FakeConnection([(value,) for value in rows])
        return SnapshotRepository(lambda: connection), connection

    def test_text_versions_are_preserved_exactly(self):
        repository, connection = self._repository(["001_init", "002_indexes"])

        self.assertEqual(
            repository.applied_schema_migrations(), ["001_init", "002_indexes"]
        )
        self.assertEqual(
            connection.cursor_instance.executed,
            ["SELECT version FROM schema_migrations ORDER BY version"],
        )
        self.assertTrue(connection.entered)
        self.assertTrue(connection.exited)
        self.assertTrue(connection.cursor_instance.entered)
        self.assertTrue(connection.cursor_instance.exited)

    def test_utf8_bytes_are_decoded_in_query_order(self):
        repository, _ = self._repository([b"001_init", b"002_indexes"])

        self.assertEqual(
            repository.applied_schema_migrations(), ["001_init", "002_indexes"]
        )

    def test_mixed_text_and_bytes_are_returned_in_query_order(self):
        repository, _ = self._repository(["001_init", b"002_indexes", "003_final"])

        self.assertEqual(
            repository.applied_schema_migrations(),
            ["001_init", "002_indexes", "003_final"],
        )

    def test_empty_results_return_empty_list(self):
        repository, _ = self._repository([])

        self.assertEqual(repository.applied_schema_migrations(), [])

    def test_invalid_utf8_bytes_raise_decoding_error(self):
        repository, _ = self._repository([b"001_init", b"\xff"])

        with self.assertRaises(UnicodeDecodeError):
            repository.applied_schema_migrations()


if __name__ == "__main__":
    unittest.main()
