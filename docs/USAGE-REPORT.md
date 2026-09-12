# Private aggregate usage report

September 12, 2026. This operator-only report summarizes the existing private beta SQLite usage ledger. It is read-only and local: it makes no provider calls, creates no analytics integration, and does not read or report conversation history. It reports counts only for active account, guest, and invitation identities; it never selects or prints their IDs or email addresses.

Run a readable seven-day report with:

```console
python -m bibleprep.usage_report --database /path/to/beta.sqlite3
```

Choose 1–366 UTC calendar days with `--days`. The window includes the current UTC day, which is partial through the report timestamp. Use `--json` or `--format json` for structured output:

```console
python -m bibleprep.usage_report --database /path/to/beta.sqlite3 --days 30 --json
```

The database path must already exist as a regular, non-symlink file. SQLite opens it with `mode=ro`, so the command cannot create the database, migrate its schema, or update records. The current `usage` schema is required; an old or unrelated database fails closed. All schema checks and aggregates use one read transaction, giving the report a consistent snapshot even if a live answer finishes while it runs.

The report includes total retained usage reservations, lifecycle-status counts, distinct active identity counts by kind, and zero-filled daily UTC totals. These are not counts of page visitors or every attempted request. Rejections that happen before a reservation, including authentication, rate-limit, allowance, terms, invalid-message, or busy checks, do not create a usage row. Once a reservation exists, the current server retains the row: a known failure before provider submission becomes a completed row with zero estimated cost and can release its quota charge; a submission whose outcome is unclear retains its full unresolved reservation.

Known cost is the sum of stored `actual_nano` estimates. Requests without an actual estimate keep their stored maximum `reserved_nano` in a separate unresolved-reservations total. Both amounts are operational ledger estimates, not reconciled provider invoices. The report does not derive inference latency: `created_unix` marks reservation creation and `updated_unix` can include queueing, application work, failure handling, or bookkeeping, so their difference is not labeled or reported as model latency.

This utility is intentionally separate from product pages and third-party analytics. Its output is suitable for private operational review, not publication or user-level analysis.
