# Spending by category and trip

Open **Spending** from the sidebar to explore expenses across all your cards.
Switch between **By category** and **Trips & groups**. Choose a period and,
when needed, a currency. **All dates** includes bookings from earlier months and
entries whose transaction dates are unknown.

## A trip such as Goa

1. Under **Trips & groups**, choose **+ New group**, enter `Goa trip`, and create it.
2. Open **Add / move entries**, select transactions, and save their assignments.
   The list initially shows ungrouped expenses. Choose **All spending** to move
   an expense from another group, or **In this group** to change existing members.
3. The trip shows net spend, charges, credits/refunds, a category breakdown and
   the included transactions. Click a breakdown row to filter the transaction
   list. These filters do not change the trip's overall totals.
4. From **Statements**, open an entry's details and choose **Trip / group** to
   assign that entry. To remove membership, choose **Ungrouped**. Bulk removal
   works the same way in Spending's assignment panel.

Each transaction has one optional group. Category, account and group are
independent: a restaurant can be **Food**, funded by **Personal**, and part of
**Goa trip**. Changing its group does not change account reconciliation, source
facts, review decisions, or automatic category/account learning.

**Manage group** renames or archives the selected group. Archiving preserves its
entries and totals while preventing new assignments. The same control can
restore an archived group. Group names are unique within your private workspace.

## Dates, totals and completeness

Spending uses reviewed **transaction dates**, while Reconciliation uses statement
months. A Summary category link preserves its month when Summary is based on
transactions; from a statement-based Summary it opens **All dates** rather than
equating a billing cycle to a calendar transaction month.

Only selected sources contribute. Repayments are excluded. Debit entries increase
charges; refunds, cashback and other credits reduce net spend. Amounts are added
as exact integer cents. Currencies remain separate and are never converted.
Unknown-currency entries have their own selection. Entries missing amount,
currency or direction remain visible but are excluded from totals; review flags
make provisional totals explicit.

The page loads every API page before showing totals, and displays transactions
in pages of 50. A batch can assign up to 50 entries atomically. If a source or
assignment changed elsewhere, the whole batch is rejected; reload and review
the current entries before retrying. Group membership follows logical entry
identity after an approved parser revision.

## Persistence and rollout

Migration **0015_spending_groups** adds owner-scoped `spending_groups`,
`spending_assignments` and append-only assignment history in `spending_events`.
Browser reads use invoker views and the existing owner RLS. Guarded RPCs require
the captured signed-in owner and expected versions; direct browser writes are
denied. Existing backup tooling includes these sidecars through app-schema
backups. Downgrade refuses to discard groups or assignment history.

Apply migrations through the existing reviewed rollout process before using
Spending against a hosted database. No automatic startup migration or hosted
database change is performed by the frontend. The explicit synthetic demo keeps
groups and assignments in memory and resets them on reload or exit.

Verification covers exact totals, dates and currencies, complete pagination,
owner isolation, atomic and stale batches, source replacement, migration round
trips and metadata drift, plus real authenticated desktop/mobile browser flows.
