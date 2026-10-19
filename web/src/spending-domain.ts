import type { Entry } from "./domain";
import { cents } from "./funding-domain";
import { reviewedValues } from "./review-domain";
import type { Label } from "./useLabels";

export type SpendingGroup = {
  id: string;
  name: string;
  is_archived: boolean;
  version: number;
};
export type SpendingEntry = Entry & {
  group_id: string | null;
  group_name: string | null;
  group_version: number;
};
export type SpendingView = "category" | "trip";
export const ungrouped = "ungrouped";
export const uncategorized = "uncategorized";

export function spendingRows(rows: SpendingEntry[], period = "all") {
  return rows.filter((row) => {
    const value = reviewedValues(row);
    return (
      row.is_selected &&
      value.entry_type !== "payment" &&
      (period === "all" || value.transaction_date?.slice(0, 7) === period)
    );
  });
}

export function spendingKey(row: SpendingEntry, view: SpendingView) {
  return view === "trip"
    ? (row.group_id ?? ungrouped)
    : (row.category_id ?? uncategorized);
}

export function spendingName(
  row: SpendingEntry,
  view: SpendingView,
  labels: Label[],
) {
  if (view === "trip") return row.group_name ?? "Ungrouped";
  return (
    labels.find((l) => l.kind === "category" && l.id === row.category_id)
      ?.name ??
    row.category_name ??
    "Uncategorized"
  );
}

export function spendingTotals(rows: SpendingEntry[]) {
  let charges = 0n,
    credits = 0n,
    incomplete = 0,
    review = 0;
  const currencies = new Set<string>();
  for (const row of rows) {
    const value = reviewedValues(row);
    if (row.needs_review) review++;
    if (value.currency) currencies.add(value.currency);
    if (value.amount === null || !value.direction || !value.currency) {
      incomplete++;
      continue;
    }
    if (value.direction === "debit") charges += cents(value.amount);
    else credits += cents(value.amount);
  }
  // Callers select one currency before adding amounts; fail rather than mix units.
  if (currencies.size > 1)
    throw Error("Select one currency for spending totals.");
  return {
    charges,
    credits,
    net: charges - credits,
    incomplete,
    review,
    count: rows.length,
  };
}

export function spendingBuckets(
  rows: SpendingEntry[],
  view: SpendingView,
  labels: Label[],
) {
  const buckets = new Map<
    string,
    { id: string; name: string; rows: SpendingEntry[] }
  >();
  for (const row of rows) {
    const id = spendingKey(row, view);
    const bucket = buckets.get(id) ?? {
      id,
      name: spendingName(row, view, labels),
      rows: [],
    };
    bucket.rows.push(row);
    buckets.set(id, bucket);
  }
  return [...buckets.values()]
    .map((bucket) => ({ ...bucket, ...spendingTotals(bucket.rows) }))
    .sort((a, b) =>
      a.net > b.net ? -1 : a.net < b.net ? 1 : a.name.localeCompare(b.name),
    );
}
