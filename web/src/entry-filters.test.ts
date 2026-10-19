// @vitest-environment jsdom
import { expect, it, vi } from "vitest";
import { readPage, type BrowserClient } from "./client";

it("filters assignments before pagination and combines them with search", async () => {
  const query = {
    select: vi.fn().mockReturnThis(),
    eq: vi.fn().mockReturnThis(),
    is: vi.fn().mockReturnThis(),
    gte: vi.fn().mockReturnThis(),
    lte: vi.fn().mockReturnThis(),
    or: vi.fn().mockReturnThis(),
    order: vi.fn().mockReturnThis(),
    range: vi.fn().mockReturnThis(),
    abortSignal: vi
      .fn()
      .mockResolvedValue({ data: [], count: 73, error: null }),
  };
  const api = {
    from: vi.fn().mockReturnValue(query),
  } as unknown as BrowserClient;
  const signal = new AbortController().signal;
  const result = await readPage(
    api,
    "statement",
    "2026-01-01",
    "2026-01-31",
    50,
    signal,
    "original",
    "newest",
    "train",
    { accountId: "household", categoryId: null },
  );
  expect(query.eq).toHaveBeenCalledWith("account_id", "household");
  expect(query.is).toHaveBeenCalledWith("category_id", null);
  expect(query.or).toHaveBeenCalledWith(
    expect.stringContaining("description.ilike"),
  );
  expect(query.range).toHaveBeenCalledWith(50, 99);
  expect(query.is.mock.invocationCallOrder[0]).toBeLessThan(
    query.range.mock.invocationCallOrder[0],
  );
  expect(result.total).toBe(73);
  vi.clearAllMocks();
  await readPage(api, "review", "", "", 0, signal);
  expect(query.eq).toHaveBeenCalledExactlyOnceWith("needs_review", true);
  expect(query.is).not.toHaveBeenCalled();
});

it("applies every column filter and sort on the server before pagination", async () => {
  const query = {
    select: vi.fn().mockReturnThis(),
    eq: vi.fn().mockReturnThis(),
    gte: vi.fn().mockReturnThis(),
    lte: vi.fn().mockReturnThis(),
    ilike: vi.fn().mockReturnThis(),
    order: vi.fn().mockReturnThis(),
    range: vi.fn().mockReturnThis(),
    abortSignal: vi
      .fn()
      .mockResolvedValue({ data: [], count: 93, error: null }),
  };
  await readPage(
    { from: () => query } as unknown as BrowserClient,
    "statement",
    "2026-01-01",
    "2026-01-31",
    50,
    new AbortController().signal,
    "original",
    "newest",
    "",
    {},
    {
      card: "Travel_%",
      type: "refund",
      direction: "credit",
      min: "9007199254740993.01",
      max: "9007199254740999.99",
      sort: { column: "amount", ascending: false },
    },
  );
  expect(query.ilike).toHaveBeenCalledWith("card_label", "%Travel\\_\\%%");
  expect(query.eq).toHaveBeenCalledWith("effective_entry_type", "refund");
  expect(query.eq).toHaveBeenCalledWith("effective_direction", "credit");
  expect(query.gte).toHaveBeenCalledWith(
    "effective_amount",
    "9007199254740993.01",
  );
  expect(query.order.mock.calls[0]).toEqual([
    "effective_amount",
    { ascending: false, nullsFirst: false },
  ]);
  expect(query.order.mock.invocationCallOrder[0]).toBeLessThan(
    query.range.mock.invocationCallOrder[0],
  );
  expect(query.range).toHaveBeenCalledWith(50, 99);
});
