// @vitest-environment jsdom
import { expect, it, vi } from "vitest";
import { readPage, type BrowserClient } from "./client";

it.each(["newest", "oldest"] as const)(
  "orders %s transaction dates on the server before pagination",
  async (sort) => {
    const query = {
      select: vi.fn().mockReturnThis(),
      eq: vi.fn().mockReturnThis(),
      gte: vi.fn().mockReturnThis(),
      lte: vi.fn().mockReturnThis(),
      order: vi.fn().mockReturnThis(),
      range: vi.fn().mockReturnThis(),
      abortSignal: vi
        .fn()
        .mockResolvedValue({ data: [], error: null, count: 0 }),
    };
    const api = { from: vi.fn().mockReturnValue(query) };
    await readPage(
      api as unknown as BrowserClient,
      "statement",
      "2026-01-01",
      "2026-01-31",
      50,
      new AbortController().signal,
      "original",
      sort,
    );
    expect(query.order.mock.calls[0]).toEqual([
      "effective_transaction_date",
      { ascending: sort === "oldest", nullsFirst: false },
    ]);
    expect(query.order.mock.calls.slice(1).map(([field]) => field)).toEqual([
      "import_id",
      "sequence",
      "id",
    ]);
    expect(query.range).toHaveBeenCalledWith(50, 99);
    expect(query.order.mock.invocationCallOrder[0]).toBeLessThan(
      query.range.mock.invocationCallOrder[0],
    );
  },
);
