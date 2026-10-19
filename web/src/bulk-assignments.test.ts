import { expect, it, vi } from "vitest";
import { saveBulkAssignments } from "./bulk-assignments";
import type { BrowserClient } from "./client";
import { demoEntries } from "./demo";

it("saves only the requested field with each transaction's version", async () => {
  const rows = [0, 1].map((i) => ({
    ...demoEntries[0],
    id: `entry-${i}`,
    is_selected: true,
    account_id: "old",
    category_id: "food",
    decision_version: i + 2,
  }));
  const rpc = vi.fn().mockResolvedValue({
    data: { account_id: "new", category_id: "food", version: 4 },
    error: null,
  });
  const result = await saveBulkAssignments(
    { rpc } as unknown as BrowserClient,
    rows,
    "account",
    "new",
  );
  expect(result.error).toBe("");
  expect(result.saved).toHaveLength(2);
  expect(rpc.mock.calls[1]).toEqual([
    "save_entry_decision",
    {
      p_entry_id: "entry-1",
      p_expected_version: 3,
      p_patch: { account_id: "new" },
    },
  ]);
  expect(result.saved.every((row) => row.category_id === "food")).toBe(true);
});

it("stops on a conflict and reports only confirmed writes", async () => {
  const rows = [0, 1, 2].map((i) => ({
    ...demoEntries[0],
    id: `entry-${i}`,
    is_selected: true,
  }));
  const rpc = vi
    .fn()
    .mockResolvedValueOnce({
      data: { account_id: "pot", category_id: null, version: 1 },
      error: null,
    })
    .mockResolvedValueOnce({ error: { code: "PT409" } });
  const result = await saveBulkAssignments(
    { rpc } as unknown as BrowserClient,
    rows,
    "category",
    null,
  );
  expect(result.saved).toHaveLength(1);
  expect(result.error).toContain("changed elsewhere");
  expect(rpc).toHaveBeenCalledTimes(2);
  expect(rpc.mock.calls[0][1].p_patch).toEqual({ category_id: null });
});

it("supports demo category updates and rejects candidate entries", async () => {
  const row = { ...demoEntries[0], is_selected: true, account_id: "pot" };
  const result = await saveBulkAssignments(null, [row], "category", "food");
  expect(result.saved[0]).toMatchObject({
    account_id: "pot",
    category_id: "food",
    decision_version: row.decision_version + 1,
  });
  expect(
    (
      await saveBulkAssignments(
        null,
        [{ ...row, is_selected: false }],
        "account",
        null,
      )
    ).saved,
  ).toHaveLength(0);
});
