"""Tests for the private, aggregate, read-only usage report."""
from contextlib import closing, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

from bibleprep import usage_report


DAY = 86400
NOW = 10 * DAY + 3600


class UsageReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "beta.sqlite3"
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("""CREATE TABLE usage(
                request_id TEXT PRIMARY KEY, invite_id TEXT,
                principal_kind TEXT NOT NULL, principal_id TEXT NOT NULL,
                quota_day INTEGER, quota_charged INTEGER NOT NULL DEFAULT 0,
                created_unix INTEGER NOT NULL, updated_unix INTEGER NOT NULL,
                reserved_nano INTEGER NOT NULL, actual_nano INTEGER,
                status TEXT NOT NULL)""")

    def tearDown(self):
        self.temporary.cleanup()

    def add(self, request_id, kind, principal, created, status, reserved, actual):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("INSERT INTO usage VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
                request_id, principal if kind == "invite" else None, kind, principal,
                created // DAY if kind == "account" else None, 1, created,
                created + 999, reserved, actual, status))
            db.commit()

    def test_aggregates_window_without_exposing_identities_or_calling_timing_latency(self):
        self.add("r1", "account", "account-uuid-private", 9 * DAY + 10, "complete", 900, 125)
        self.add("r2", "account", "account-uuid-private", 10 * DAY, "uncertain", 700, None)
        self.add("r3", "guest", "guest-hmac-private", NOW, "complete", 800, 250)
        self.add("r4", "invite", "invite-private", 10 * DAY + 20, "submitted", 600, None)
        self.add("old", "account", "old-private", 8 * DAY + 100, "complete", 500, 500)
        self.add("future", "guest", "future-private", NOW + 1, "running", 400, None)

        report = usage_report.build_report(self.database, days=2, now=NOW)

        self.assertEqual(report["requests"], 4)
        self.assertEqual(report["statuses"]["complete"], 2)
        self.assertEqual(report["statuses"]["uncertain"], 1)
        self.assertEqual(report["statuses"]["submitted"], 1)
        self.assertEqual(report["active_identities"], {
            "accounts": 1, "guests": 1, "invites": 1, "other": 0})
        self.assertEqual(report["cost"]["estimated_known_nano_usd"], 375)
        self.assertEqual(report["cost"]["unresolved_reserved_nano_usd"], 1300)
        self.assertEqual(report["cost"]["unresolved_requests"], 2)
        self.assertEqual([day["requests"] for day in report["daily"]], [1, 3])
        encoded = json.dumps(report)
        for private in ("account-uuid-private", "guest-hmac-private", "invite-private",
                        "old-private", "future-private"):
            self.assertNotIn(private, encoded)
        self.assertNotIn("latency", encoded.casefold())

    def test_empty_window_includes_zero_filled_utc_days(self):
        report = usage_report.build_report(self.database, days=3, now=NOW)
        self.assertEqual(report["requests"], 0)
        self.assertEqual(report["active_identities"], {
            "accounts": 0, "guests": 0, "invites": 0, "other": 0})
        self.assertTrue(all(value == 0 for value in report["statuses"].values()))
        self.assertEqual([day["date_utc"] for day in report["daily"]],
                         ["1970-01-09", "1970-01-10", "1970-01-11"])
        self.assertTrue(all(day["requests"] == 0 for day in report["daily"]))

    def test_read_only_open_does_not_create_or_change_database(self):
        before = self.database.read_bytes()
        usage_report.build_report(self.database, days=1, now=NOW)
        self.assertEqual(self.database.read_bytes(), before)
        missing = Path(self.temporary.name) / "missing.sqlite3"
        with self.assertRaisesRegex(usage_report.UsageReportError, "existing regular"):
            usage_report.build_report(missing, now=NOW)
        self.assertFalse(missing.exists())

    def test_all_aggregates_share_one_snapshot_during_a_live_write(self):
        self.add("first", "guest", "guest-one", NOW, "complete", 100, 25)
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("PRAGMA journal_mode=WAL")

        original_open = usage_report._open_read_only

        class WriteAfterOverallQuery:
            def __init__(inner_self, connection):
                inner_self.connection = connection
                inner_self.injected = False

            def execute(inner_self, sql, parameters=()):
                cursor = inner_self.connection.execute(sql, parameters)
                if "SELECT COUNT(*)," in sql and not inner_self.injected:
                    inner_self.injected = True
                    with closing(sqlite3.connect(self.database)) as writer:
                        writer.execute("INSERT INTO usage VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
                            "concurrent", None, "account", "account-two", None, 1,
                            NOW, NOW, 200, 50, "complete"))
                        writer.commit()
                return cursor

            def close(inner_self):
                inner_self.connection.close()

        def open_with_injection(path):
            return WriteAfterOverallQuery(original_open(path))

        with mock.patch.object(usage_report, "_open_read_only", open_with_injection):
            report = usage_report.build_report(self.database, days=1, now=NOW)

        self.assertEqual(report["requests"], 1)
        self.assertEqual(sum(report["statuses"].values()), 1)
        self.assertEqual(sum(day["requests"] for day in report["daily"]), 1)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM usage").fetchone()[0], 2)

    def test_days_and_schema_are_validated(self):
        for value in (0, -1, True, 367, 1.5):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "days"):
                usage_report.build_report(self.database, days=value, now=NOW)
        invalid = Path(self.temporary.name) / "other.sqlite3"
        with closing(sqlite3.connect(invalid)) as db:
            db.execute("CREATE TABLE something_else(value TEXT)")
        with self.assertRaisesRegex(usage_report.UsageReportError, "usage schema"):
            usage_report.build_report(invalid, now=NOW)

    def test_cli_prints_json_or_readable_summary(self):
        self.add("r1", "guest", "never-print-me", int(time.time()), "complete", 100, 25)
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(usage_report.main([
                "--database", str(self.database), "--days", "1", "--json"]), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["requests"], 1)
        self.assertNotIn("never-print-me", output.getvalue())

        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(usage_report.main([
                "--database", str(self.database), "--days", "1"]), 0)
        summary = output.getvalue()
        self.assertIn("Requests: 1", summary)
        self.assertIn("retained usage reservations", summary)
        self.assertIn("not an invoice", summary)
        self.assertNotIn("never-print-me", summary)


if __name__ == "__main__":
    unittest.main()
