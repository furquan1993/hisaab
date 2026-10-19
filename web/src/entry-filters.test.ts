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
