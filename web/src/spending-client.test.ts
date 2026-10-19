// @vitest-environment jsdom
import { expect, it, vi } from "vitest";
import type { BrowserClient } from "./client";
import { demoEntries } from "./demo";
import { readSpending } from "./spending-client";

function setup(
  pages: { data: unknown[] | null; count: number | null; error: unknown }[],
) {
  const query = {
    select: vi.fn().mockReturnThis(),
    order: vi.fn().mockReturnThis(),
    range: vi.fn().mockReturnThis(),
    abortSignal: vi.fn(),
  };
  pages.forEach((p) => query.abortSignal.mockResolvedValueOnce(p));
  const empty = {
    select: vi.fn().mockReturnThis(),
    order: vi.fn().mockReturnThis(),
    range: vi.fn().mockReturnThis(),
    abortSignal: vi.fn().mockResolvedValue({ data: [], error: null, count: 0 }),
  };
  const api = {
    from: vi.fn((name: string) =>
      name === "spending_entries" ? query : empty,
    ),
  } as unknown as BrowserClient;
  return { api, query };
}
const row = (id: string) => ({
  ...demoEntries[0],
  id,
  group_id: null,
  group_name: null,
  group_version: 0,
});
it("loads every page before returning spending, with stable ordering and inclusive ranges", async () => {
  const rows = Array.from({ length: 121 }, (_, i) => row(String(i)));
  const { api, query } = setup([
    { data: rows.slice(0, 100), count: 121, error: null },
    { data: rows.slice(100), count: 121, error: null },
  ]);
  expect(
    (await readSpending(api, new AbortController().signal)).rows,
  ).toHaveLength(121);
  expect(query.range.mock.calls).toEqual([
    [0, 99],
    [100, 199],
  ]);
  expect(query.order).toHaveBeenCalledWith("id");
});
it("rejects failed, overlapping and incomplete later pages instead of showing partial totals", async () => {
  for (const page of [
    { data: null, count: null, error: {} },
    { data: [row("first")], count: 2, error: null },
    { data: [], count: 2, error: null },
  ]) {
    const { api } = setup([
      { data: [row("first")], count: 2, error: null },
      page,
    ]);
    await expect(
      readSpending(api, new AbortController().signal),
    ).rejects.toThrow();
  }
});
