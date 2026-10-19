import { expect, it } from "vitest";
import { demoEntries } from "./demo";
import {
  spendingBuckets,
  spendingRows,
  spendingTotals,
  type SpendingEntry,
} from "./spending-domain";

const row = (patch: Partial<SpendingEntry> = {}): SpendingEntry => ({
  ...demoEntries[0],
  is_selected: true,
  needs_review: false,
  amount: "100.00",
  direction: "debit",
  currency: "INR",
  entry_type: "purchase",
  group_id: "goa",
  group_name: "Goa trip",
  group_version: 1,
  ...patch,
});

it("uses reviewed transaction dates, excludes candidate sources and repayments, and retains undated spending for all dates", () => {
  const rows = [
    row({ effective_transaction_date: "2026-02-01" }),
    row({ transaction_date: null }),
    row({ effective_entry_type: "payment" }),
    row({ is_selected: false }),
  ];
  expect(spendingRows(rows)).toHaveLength(2);
  expect(spendingRows(rows, "2026-02")).toEqual([rows[0]]);
});
it("keeps exact charges and credits, negative net spending and incomplete facts explicit", () => {
  const totals = spendingTotals([
    row({ amount: "0.10" }),
    row({ direction: "credit", amount: "50.20" }),
    row({ effective_amount: null, needs_review: true }),
  ]);
  expect(totals).toMatchObject({
    charges: 10n,
    credits: 5020n,
    net: -5010n,
    incomplete: 1,
    review: 1,
    count: 3,
  });
  expect(() => spendingTotals([row(), row({ currency: "USD" })])).toThrow(
    "one currency",
  );
  expect(spendingTotals([row({ amount: "999999999999999999.99" })]).net).toBe(
    99999999999999999999n,
  );
});
it("groups trips independently of account/category and uses current label names", () => {
  const rows = [
    row({
      category_id: "food",
      category_name: "Old food",
      account_id: "personal",
    }),
    row({ category_id: "food", account_id: "travel" }),
    row({ group_id: null, group_name: null }),
  ];
  const trips = spendingBuckets(rows, "trip", []);
  expect(trips[0]).toMatchObject({ id: "goa", net: 20000n, count: 2 });
  expect(trips[1].name).toBe("Ungrouped");
  const categories = spendingBuckets(rows, "category", [
    {
      id: "food",
      name: "Food",
      kind: "category",
      is_archived: false,
      version: 1,
    },
  ]);
  expect(categories[0]).toMatchObject({ name: "Food", count: 2 });
});
