import unittest
from pathlib import Path

from scripts.ci.check_migrations import migration_checksums, read_sql
from storage.repository import SnapshotRepository


ROOT = Path(__file__).resolve().parents[1]


class FilingWorkLedgerContractTests(unittest.TestCase):
    def test_migration_007_is_a_utf8_reversible_pair(self):
        migrations = ROOT / "storage/migrations"
        checksums = migration_checksums(migrations)
        self.assertEqual(len(checksums), 7)
        self.assertIn("007_filing_work_ledger", checksums)
        self.assertIn("CREATE TABLE filing_work_items", read_sql(migrations / "007_filing_work_ledger.up.sql"))
        self.assertIn("CREATE TABLE filing_work_attempts", read_sql(migrations / "007_filing_work_ledger.up.sql"))

    def test_repository_exposes_durable_ledger_seams(self):
        expected = {
            "sync_reviewed_filings",
            "get_filing_work_statuses",
            "claim_filing_work",
            "renew_filing_work",
            "finalize_filing_work",
            "expire_filing_work_leases",
            "get_filing_attempt_history",
            "get_filing_work_counts",
        }
        self.assertTrue(expected.issubset(set(dir(SnapshotRepository))))

    def test_roles_do_not_grant_delete_or_bot_ledger_access(self):
        roles = (ROOT / "storage/supabase_roles.sql").read_text()
        self.assertNotIn("DELETE ON filing_work_", roles)
        bot_grants = [line for line in roles.splitlines() if "TO pasticuan_bot" in line]
        self.assertFalse(any("filing_work_" in grant for grant in bot_grants))


if __name__ == "__main__":
    unittest.main()
