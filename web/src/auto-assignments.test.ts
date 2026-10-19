import { expect, it, vi } from "vitest";
import type { BrowserClient } from "./client";
import { demoEntries } from "./demo";
import { assignEntries } from "./auto-assignments";

function api(result: { data: unknown; error: unknown }) {
  const abortSignal = vi.fn().mockResolvedValue(result);
  const rpc = vi.fn().mockReturnValue({ abortSignal });
  return { client: { rpc } as unknown as BrowserClient, rpc };
}
it("assigns selected unassigned entries with captured ownership", async () => {
  const mock = api({ data: 1, error: null });
  const row = { ...demoEntries[0], is_selected: true, account_id: null };
  const candidate = { ...row, id: "candidate", is_selected: false };
  expect(
    await assignEntries(
      mock.client,
      "owner",
      [row, candidate],
      new AbortController().signal,
    ),
  ).toBe(1);
  expect(mock.rpc).toHaveBeenCalledWith("auto_assign_entries", {
    p_entry_ids: [row.id],
    p_expected_owner: "owner",
  });
});
it("skips complete assignments and reports unconfirmed writes", async () => {
  const mock = api({ data: null, error: { code: "PT409" } });
  const row = {
    ...demoEntries[0],
    is_selected: true,
    account_id: "a",
    category_id: "c",
  };
  expect(
    await assignEntries(
      mock.client,
      "owner",
      [row],
      new AbortController().signal,
    ),
  ).toBe(0);
  expect(mock.rpc).not.toHaveBeenCalled();
  await expect(
    assignEntries(
      mock.client,
      "owner",
      [{ ...row, category_id: null }],
      new AbortController().signal,
    ),
  ).rejects.toThrow("Automatic assignments are unavailable");
});
it("validates the server response", async () => {
  const mock = api({ data: 51, error: null });
  await expect(
    assignEntries(
      mock.client,
      "owner",
      [{ ...demoEntries[0], is_selected: true, account_id: null }],
      new AbortController().signal,
    ),
  ).rejects.toThrow();
});
