import { describe, expect, it } from "vitest";
import { entrySchema, filterEntries, formatAmount, type Entry } from "./domain";

const row = (changes: Partial<Entry> = {}): Entry =>
  entrySchema.parse({
    id: "a",
    import_id: "i",
    statement_id: "s",
    card_label: "Demo card",
    bank: "hdfc",
    statement_date: "2026-01-31",
    transaction_date: "2025-12-30",
    description: "Invented shop",
    amount: "123.45",
    direction: "debit",
    currency: "INR",
    entry_type: "purchase",
    sequence: 1,
    is_selected: true,
    needs_review: false,
    entry_issues: [],
    import_issues: [],
    review_status: "pending",
    ...changes,
  });
describe("independent date views", () => {
  it("includes every selected entry in matching bills, even outside transaction range", () => {
    expect(
      filterEntries([row()], "statement", "2026-01-01", "2026-01-31"),
    ).toHaveLength(1);
    expect(
      filterEntries([row()], "transaction", "2026-01-01", "2026-01-31"),
    ).toHaveLength(0);
  });
  it("includes matching transactions from a later bill and inclusive endpoints", () => {
    const rows = [
      row({ transaction_date: "2026-01-01", statement_date: "2026-02-28" }),
      row({ id: "b", transaction_date: "2026-01-31" }),
    ];
    expect(
      filterEntries(rows, "transaction", "2026-01-01", "2026-01-31"),
    ).toHaveLength(2);
  });
  it("keeps candidates separate and unknown dates in an all-date review queue", () => {
    const rows = [
      row({ is_selected: false, needs_review: true }),
      row({ transaction_date: null, needs_review: true }),
    ];
    expect(
      filterEntries(rows, "transaction", "2026-01-01", "2026-01-31"),
    ).toHaveLength(0);
    expect(
      filterEntries(rows, "statement", "2026-01-01", "2026-01-31"),
    ).toHaveLength(1);
    expect(
      filterEntries(rows, "review", "2026-01-01", "2026-01-31"),
    ).toHaveLength(2);
  });
  it("does not deduplicate identical-looking purchases", () => {
    expect(
      filterEntries(
        [row(), row({ id: "b" })],
        "statement",
        "2026-01-01",
        "2026-01-31",
      ),
    ).toHaveLength(2);
  });
});
describe("exact financial display", () => {
  it("never coerces money through floating point", () => {
    expect(formatAmount("999999999999999999.99", "INR", "debit")).toBe(
      "− INR 9,99,99,99,99,99,99,99,999.99",
    );
  });
  it("does not guess missing money or direction", () => {
    expect(formatAmount(null, "INR", "debit")).toBe("Amount unknown");
    expect(formatAmount("1.00", null, null)).toBe("? 1.00");
  });
});
