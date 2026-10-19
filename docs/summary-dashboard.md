# Summary dashboard

Open **Summary** in the workspace sidebar. Pick a month and choose statement
month (the default) or transaction month. **View entries** opens that same month
and date basis using reviewed dates; **View reconciliation** opens the selected
month's funding balances.

Each currency has its own **Net spending this cycle** (or **Net spending in month**
in transaction mode), charges and credits, with breakdowns by card, category and
budget account. Net spending is charges minus credits. Card
repayments are excluded using the reviewed entry type. Refunds, cashback,
reversals and other credits reduce spend; a negative total remains visible.
Unassigned entries remain in the breakdowns. Contributions do not affect spend.

The dashboard uses selected imported entries, reviewed amounts and dates, and
exact integer minor units. It loads every matching page before displaying live
totals. A failed page displays an error rather than a partial total. Month or
date-basis changes hide the previous totals while the next month loads.

Entries with unknown amounts, directions or currencies are excluded from money
totals and counted in a warning. Review flags remain visible even when an amount
can be included. Selected entries with no reviewed date are counted across all
imports because they cannot be assigned to a month. Check Imports for missing
statements or competing sources: the dashboard covers imported selected entries,
not independently verified statement coverage.

The synthetic demo uses the same aggregation rules without accessing live data.

In Statement month mode, **Statement bills** shows each selected statement's
**Statement amount due** exactly as printed. Expand **How this bill adds up** to
see the previous balance, payments and credits received, charges, finance charges,
and the calculated amount due. Any difference from the printed bill is shown
explicitly; it is not silently attributed to rounding. Payments affect bill
balances, while spending excludes them. Funding contributions remain separate.

Printed balances are captured from the observed HDFC five-column header with
page, bounding box and source text. Unsupported, ambiguous or missing headers
remain unknown; the page shows **Not captured**. Other banks' printed headers
are not inferred from transaction totals. Bill balances are not presented in
transaction-month mode because a transaction month can span several bill cycles.

Migration `0014_statement_balances` adds a nullable `imports.printed_balance` field
and the owner-scoped, read-only `hisaab_api.statement_bills` view. Existing imports
remain unchanged until explicitly backfilled. The frontend still shows spending
and a separate bill-data status when that view is unavailable.

`core.statement_balance_capture.capture_printed_balance` previews filling missing
evidence by default. It checks the original PDF fingerprint, statement metadata,
and all extracted transaction/source fields against the import before saving.
It never overwrites different printed evidence, transaction facts, selected
sources or decisions. Hosted migration and financial backfill require the
repository's separate reviewed rollout approval and a verified backup.
