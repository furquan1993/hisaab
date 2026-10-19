import { expect, it } from "vitest";
import { demoEntries } from "./demo";
import { summarizeSpend } from "./summary-domain";
import type { Entry } from "./domain";

const row = (changes: Partial<Entry> = {}): Entry => ({
  ...demoEntries[0],
  is_selected: true,
  needs_review: false,
  amount: "100.00",
  direction: "debit",
  entry_type: "purchase",
  ...changes,
});

it("excludes reviewed repayments, keeps refunds and currencies separate, and preserves repeated purchases", () => {
  const result = summarizeSpend([
    row(),
    row({ id: "repeat" }),
    row({ entry_type: "payment", amount: "9999.00", direction: "credit" }),
    row({ effective_entry_type: "payment" }),
    row({
      entry_type: "payment",
      effective_entry_type: "refund",
      direction: "credit",
      amount: "20.10",
    }),
    row({ entry_type: "cashback", direction: "credit", amount: "0.20" }),
    row({ currency: "USD", amount: "999999999999999999.99" }),
    row({ is_selected: false }),
    row({ effective_amount: null, needs_review: true }),
  ]);
  expect(result.payments).toBe(2);
  expect(result.incomplete).toBe(1);
  expect(result.review).toBe(1);
  expect(result.entries).toBe(6);
  const [inr, usd] = result.currencies;
  expect(inr.charges - inr.credits).toBe(17970n);
  expect(inr.categories.get("unassigned")?.count).toBe(4);
  expect(usd.charges).toBe(99999999999999999999n);
});

it("retains negative spend and uses reviewed amounts and assignments", () => {
  const result = summarizeSpend([
    row({
      category_id: "food",
      category_name: "Food",
      account_id: "pot",
      account_name: "Household",
      effective_amount: "0.10",
    }),
    row({ entry_type: "refund", amount: "50.00", direction: "credit" }),
  ]);
  expect(result.currencies[0].charges - result.currencies[0].credits).toBe(
    -4990n,
  );
  expect(result.currencies[0].categories.get("food")?.charges).toBe(10n);
  expect(result.currencies[0].accounts.get("pot")?.name).toBe("Household");
  expect(summarizeSpend([]).currencies).toEqual([]);
});
