// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { readPage, type BrowserClient } from "./client";
import { demoEntries } from "./demo";
import { readSummary } from "./summary-client";

vi.mock("./client", async (original) => ({
  ...(await original<typeof import("./client")>()),
  readPage: vi.fn(),
}));
afterEach(() => vi.clearAllMocks());
function client() {
  const query = {
    select: vi.fn().mockReturnThis(),
    eq: vi.fn().mockReturnThis(),
    is: vi.fn().mockReturnThis(),
    abortSignal: vi.fn().mockResolvedValue({ error: null, count: 3 }),
  };
  return {
    query,
    api: { from: vi.fn().mockReturnValue(query) } as unknown as BrowserClient,
  };
}
it("loads beyond the first 50 rows and uses reviewed dates for the entire month", async () => {
  const { api, query } = client();
  const entries = Array.from({ length: 121 }, (_, index) => ({
    ...demoEntries[0],
    id: String(index),
  }));
  vi.mocked(readPage).mockImplementation(
    async (_api, _view, _start, _end, offset) => ({
      rows: entries.slice(offset, offset + 50),
      total: 121,
    }),
  );
  const signal = new AbortController().signal;
  const loaded = await readSummary(api, "2024-02", "transaction", signal);
  expect(loaded.rows).toHaveLength(121);
  expect(loaded.undated).toBe(3);
  expect(vi.mocked(readPage).mock.calls.map((call) => call[4])).toEqual([
    0, 50, 100,
  ]);
  expect(readPage).toHaveBeenLastCalledWith(
    api,
    "transaction",
    "2024-02-01",
    "2024-02-29",
    100,
    signal,
    "reviewed",
  );
  expect(query.is).toHaveBeenCalledWith("effective_transaction_date", null);
  expect(query.select).toHaveBeenCalledWith("id", {
    count: "exact",
    head: true,
  });
  expect(api.from).not.toHaveBeenCalledWith("statement_bills");
});

it("keeps spending available when printed bill balances cannot be loaded", async () => {
  const { api } = client();
  vi.mocked(readPage).mockResolvedValue({ rows: [demoEntries[0]], total: 1 });
  const result = await readSummary(
    api,
    "2026-01",
    "statement",
    new AbortController().signal,
  );
  expect(result.rows).toHaveLength(1);
  expect(result.bills).toEqual([]);
  expect(result.billsError).toContain(
    "Printed bill balances could not be loaded",
  );
});

it("rejects a failed later page instead of presenting a partial total", async () => {
  const { api } = client();
  vi.mocked(readPage)
    .mockResolvedValueOnce({ rows: [demoEntries[0]], total: 2 })
    .mockRejectedValueOnce(Error("Connection lost"));
  await expect(
    readSummary(api, "2026-01", "statement", new AbortController().signal),
  ).rejects.toThrow("Connection lost");
});

it("rejects overlapping pages when entries change during loading", async () => {
  const { api } = client();
  vi.mocked(readPage).mockResolvedValue({ rows: [demoEntries[0]], total: 2 });
  await expect(
    readSummary(api, "2026-01", "statement", new AbortController().signal),
  ).rejects.toThrow("Entries changed");
});
