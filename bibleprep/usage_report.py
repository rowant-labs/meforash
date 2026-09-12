"""Read-only aggregate usage report for the private beta SQLite ledger.

The report reads request metadata and cost estimates only. It never selects or
prints principal identifiers, authentication records, prompts, or answers.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


NANO_USD = 1_000_000_000
MAX_REPORT_DAYS = 366
KNOWN_STATUSES = ("complete", "uncertain", "reserved", "submitted", "running")
REQUIRED_USAGE_COLUMNS = {
    "request_id", "invite_id", "principal_kind", "principal_id", "quota_day",
    "quota_charged", "created_unix", "updated_unix", "reserved_nano",
    "actual_nano", "status",
}


class UsageReportError(RuntimeError):
    """The ledger could not be safely read as a current beta usage database."""


def _iso_utc(unix):
    return datetime.fromtimestamp(unix, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _usd(nano):
    whole, fraction = divmod(nano, NANO_USD)
    return f"{whole}.{fraction:09d}"


def _validate_days(days):
    if type(days) is not int or not 1 <= days <= MAX_REPORT_DAYS:
        raise ValueError(f"days must be an integer from 1 through {MAX_REPORT_DAYS}")


def _open_read_only(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise UsageReportError("The usage database must be an existing regular non-symlink file.")
    try:
        # SQLite's mode=ro is the enforcement boundary: it cannot create the
        # database or write schema/data while producing this report.
        return sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise UsageReportError("The usage database could not be opened read-only.") from exc


def _cost(known_nano, unresolved_nano, unresolved_requests):
    return {
        "estimated_known_nano_usd": known_nano,
        "estimated_known_usd": _usd(known_nano),
        "unresolved_reserved_nano_usd": unresolved_nano,
        "unresolved_reserved_usd": _usd(unresolved_nano),
        "unresolved_requests": unresolved_requests,
        "basis": "ledger_estimate_and_reservation_not_invoice",
    }


def build_report(database, *, days=7, now=None):
    """Return aggregate usage for UTC calendar days through ``now``.

    The current UTC day is included and is partial through the supplied second.
    ``now`` exists for deterministic operator checks and tests.
    """
    _validate_days(days)
    if now is None:
        now = int(datetime.now(tz=timezone.utc).timestamp())
    if type(now) is not int or now < 0:
        raise ValueError("now must be a non-negative Unix timestamp")
    day_start = now - now % 86400
    start = day_start - (days - 1) * 86400
    end_exclusive = now + 1

    try:
        with closing(_open_read_only(database)) as db:
            # Keep schema validation and every aggregate on one snapshot. Without
            # this explicit transaction, each SELECT could observe a different
            # ledger state while a live request is being finalized.
            db.execute("BEGIN")
            table = db.execute(
                "SELECT type FROM sqlite_master WHERE name='usage'"
            ).fetchone()
            columns = {row[1] for row in db.execute("PRAGMA table_info(usage)")}
            if table != ("table",) or not REQUIRED_USAGE_COLUMNS.issubset(columns):
                raise UsageReportError("The database does not contain the current beta usage schema.")

            parameters = (start, end_exclusive)
            total, known_nano, unresolved_nano, unresolved_requests = db.execute(
                """SELECT COUNT(*),
                          COALESCE(SUM(CASE WHEN actual_nano IS NOT NULL
                                           THEN actual_nano ELSE 0 END), 0),
                          COALESCE(SUM(CASE WHEN actual_nano IS NULL
                                           THEN reserved_nano ELSE 0 END), 0),
                          COALESCE(SUM(CASE WHEN actual_nano IS NULL THEN 1 ELSE 0 END), 0)
                     FROM usage
                    WHERE created_unix>=? AND created_unix<?""",
                parameters,
            ).fetchone()
            status_rows = db.execute(
                """SELECT status, COUNT(*) FROM usage
                    WHERE created_unix>=? AND created_unix<?
                    GROUP BY status ORDER BY status""",
                parameters,
            ).fetchall()
            identity_rows = db.execute(
                """SELECT principal_kind, COUNT(DISTINCT principal_id) FROM usage
                    WHERE created_unix>=? AND created_unix<?
                    GROUP BY principal_kind ORDER BY principal_kind""",
                parameters,
            ).fetchall()
            daily_rows = db.execute(
                """SELECT created_unix / 86400 AS utc_day, status, COUNT(*),
                          COALESCE(SUM(CASE WHEN actual_nano IS NOT NULL
                                           THEN actual_nano ELSE 0 END), 0),
                          COALESCE(SUM(CASE WHEN actual_nano IS NULL
                                           THEN reserved_nano ELSE 0 END), 0),
                          COALESCE(SUM(CASE WHEN actual_nano IS NULL THEN 1 ELSE 0 END), 0)
                     FROM usage
                    WHERE created_unix>=? AND created_unix<?
                    GROUP BY utc_day, status ORDER BY utc_day, status""",
                parameters,
            ).fetchall()
    except UsageReportError:
        raise
    except sqlite3.Error as exc:
        raise UsageReportError("The beta usage records could not be read.") from exc

    statuses = {status: 0 for status in KNOWN_STATUSES}
    for status, count in status_rows:
        statuses[status] = count

    active = {"accounts": 0, "guests": 0, "invites": 0, "other": 0}
    labels = {"account": "accounts", "guest": "guests", "invite": "invites"}
    for kind, count in identity_rows:
        active[labels.get(kind, "other")] += count

    daily_by_number = {}
    for offset in range(days):
        number = start // 86400 + offset
        daily_by_number[number] = {
            "date_utc": datetime.fromtimestamp(number * 86400, tz=timezone.utc).date().isoformat(),
            "requests": 0,
            "statuses": {status: 0 for status in KNOWN_STATUSES},
            "cost": _cost(0, 0, 0),
        }
    for number, status, count, known, unresolved, unresolved_count in daily_rows:
        day = daily_by_number[number]
        day["requests"] += count
        day["statuses"][status] = count
        day["cost"] = _cost(
            day["cost"]["estimated_known_nano_usd"] + known,
            day["cost"]["unresolved_reserved_nano_usd"] + unresolved,
            day["cost"]["unresolved_requests"] + unresolved_count,
        )

    return {
        "schema_version": 1,
        "kind": "private_beta_aggregate_usage",
        "generated_at_utc": _iso_utc(now),
        "window": {
            "days": days,
            "start_utc": _iso_utc(start),
            "through_utc": _iso_utc(now),
            "current_day_is_partial": True,
        },
        "count_basis": "retained_usage_reservations_not_attempts_or_page_visitors",
        "requests": total,
        "statuses": statuses,
        "active_identities": active,
        "cost": _cost(known_nano, unresolved_nano, unresolved_requests),
        "daily": list(daily_by_number.values()),
    }


def format_summary(report):
    """Render a compact operator-readable report without identity values."""
    window = report["window"]
    statuses = ", ".join(f"{key} {value}" for key, value in report["statuses"].items())
    active = report["active_identities"]
    cost = report["cost"]
    lines = [
        f"Private beta usage: {window['start_utc']} through {window['through_utc']} UTC",
        f"Requests: {report['requests']} ({statuses})",
        "Count basis: retained usage reservations, not all attempts or page visitors.",
        ("Distinct active identities: "
         f"accounts {active['accounts']}, guests {active['guests']}, "
         f"invites {active['invites']}, other {active['other']}"),
        f"Estimated known cost: ${cost['estimated_known_usd']}",
        (f"Unresolved reservations: ${cost['unresolved_reserved_usd']} "
         f"across {cost['unresolved_requests']} request(s)"),
        "Cost figures are ledger estimates and reservations, not an invoice.",
        "Daily UTC totals:",
    ]
    for day in report["daily"]:
        lines.append(
            f"  {day['date_utc']}: {day['requests']} request(s), "
            f"known ${day['cost']['estimated_known_usd']}, "
            f"unresolved ${day['cost']['unresolved_reserved_usd']}"
        )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, help="Existing private beta SQLite ledger")
    parser.add_argument("--days", type=int, default=7,
                        help=f"UTC calendar days through today (1-{MAX_REPORT_DAYS}; default: 7)")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    output.add_argument("--format", choices=("summary", "json"), default="summary",
                        help="Output format (default: summary)")
    args = parser.parse_args(argv)
    try:
        report = build_report(args.database, days=args.days)
    except (UsageReportError, ValueError) as exc:
        parser.exit(1, f"usage report: {exc}\n")
    if args.json or args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
