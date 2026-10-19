// @vitest-environment jsdom
import { expect, it, vi } from "vitest";
import type { BrowserClient } from "./client";
import { readStatementBills, type StatementBill } from "./statement-bills";

it("loads selected bill summaries beyond the API page size with stable month ordering", async () => {
  const bill: StatementBill = {
    id: "import",
    statement_id: "statement",
    card_id: "card",
    card_label: "Invented card",
    bank: "hdfc",
    statement_date: "2026-01-31",
    printed_statement_date: "2026-01-31",
    printed_balance: null,
  };
  const query = {
    select: vi.fn().mockReturnThis(),
    gte: vi.fn().mockReturnThis(),
    lte: vi.fn().mockReturnThis(),
    order: vi.fn().mockReturnThis(),
    range: vi.fn().mockReturnThis(),
    abortSignal: vi
      .fn()
      .mockResolvedValueOnce({
        data: Array.from({ length: 100 }, (_, i) => ({
          ...bill,
          id: String(i),
        })),
        error: null,
      })
      .mockResolvedValueOnce({ data: [{ ...bill, id: "last" }], error: null }),
  };
  const api = { from: vi.fn().mockReturnValue(query) };
  const result = await readStatementBills(
    api as unknown as BrowserClient,
    "2026-01-01",
    "2026-01-31",
    new AbortController().signal,
  );
  expect(result).toHaveLength(101);
  expect(query.range.mock.calls).toEqual([
    [0, 99],
    [100, 199],
  ]);
  expect(query.order.mock.calls.slice(0, 3)).toEqual([
    ["card_id"],
    ["statement_date"],
    ["id"],
  ]);
  expect(query.gte).toHaveBeenCalledWith("statement_date", "2026-01-01");
  expect(query.lte).toHaveBeenCalledWith("statement_date", "2026-01-31");
});
