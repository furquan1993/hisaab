// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import Workspace from "./Workspace";
import { readPage, type BrowserClient } from "./client";
import { demoEntries } from "./demo";
const { reload } = vi.hoisted(() => ({ reload: vi.fn() }));
vi.mock("./client", async (original) => ({
  ...(await original<typeof import("./client")>()),
  readPage: vi.fn(),
}));
vi.mock("./useLabels", () => ({
  useLabels: () => ({
    labels: [
      {
        id: "account",
        kind: "account",
        name: "History pot",
        is_archived: false,
        version: 1,
      },
      {
        id: "category",
        kind: "category",
        name: "Groceries",
        is_archived: false,
        version: 1,
      },
    ],
    loading: false,
    error: "",
    reload,
  }),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
it("reloads persisted automatic decisions and refreshed labels before showing the ledger", async () => {
  const row = {
    ...demoEntries[0],
    is_selected: true,
    account_id: null,
    category_id: null,
  };
  const saved = {
    ...row,
    account_id: "account",
    category_id: "category",
    decision_version: 1,
  };
  vi.mocked(readPage)
    .mockResolvedValueOnce({ rows: [row], total: 1 })
    .mockResolvedValue({ rows: [saved], total: 1 });
  const rpc = vi.fn().mockReturnValue({
    abortSignal: vi.fn().mockResolvedValue({ data: 1, error: null }),
  });
  render(
    <Workspace
      api={{ rpc } as unknown as BrowserClient}
      owner="Owner"
      ownerId="owner-id"
      initialRange={["2026-01-01", "2026-01-31"]}
      onExit={() => {}}
    />,
  );
  await screen.findByText(row.description);
  expect(
    (
      screen.getByLabelText(
        `Account for ${row.description}`,
      ) as HTMLSelectElement
    ).value,
  ).toBe("account");
  expect(
    (
      screen.getByLabelText(
        `Category for ${row.description}`,
      ) as HTMLSelectElement
    ).value,
  ).toBe("category");
  expect(reload).toHaveBeenCalledTimes(1);
  expect(readPage).toHaveBeenCalledTimes(2);
  expect(vi.mocked(readPage).mock.calls[1][7]).toBe("newest");
});
it("keeps the ledger available and shows an assignment failure without retrying writes", async () => {
  const row = {
    ...demoEntries[0],
    is_selected: true,
    account_id: null,
    category_id: null,
  };
  vi.mocked(readPage).mockResolvedValue({ rows: [row], total: 1 });
  const rpc = vi.fn().mockReturnValue({
    abortSignal: vi
      .fn()
      .mockResolvedValue({ data: null, error: { code: "PT409" } }),
  });
  render(
    <Workspace
      api={{ rpc } as unknown as BrowserClient}
      owner="Owner"
      ownerId="owner-id"
      initialRange={["2026-01-01", "2026-01-31"]}
      onExit={() => {}}
    />,
  );
  await screen.findByText(row.description);
  expect(
    screen.getByText(/Automatic assignments are unavailable/),
  ).toBeTruthy();
  await waitFor(() => expect(rpc).toHaveBeenCalledTimes(1));
  expect(readPage).toHaveBeenCalledTimes(1);
});
