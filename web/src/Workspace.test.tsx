// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Workspace from "./Workspace";
import { readPage, type BrowserClient } from "./client";
import { demoEntries } from "./demo";
vi.mock("./client", async (original) => ({
  ...(await original<typeof import("./client")>()),
  readPage: vi.fn(),
}));
vi.mock("./useLabels", () => ({
  useLabels: () => ({
    labels: [
      { id: "pot", kind: "account", name: "Household", is_archived: false },
      { id: "food", kind: "category", name: "Food", is_archived: false },
    ],
    loading: false,
    error: "",
  }),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
it("saves consecutive inline edits without reloading or replacing the list and preserves values on failure", async () => {
  const user = userEvent.setup();
  const row = {
    ...demoEntries.find((entry) => entry.is_selected)!,
    account_id: null,
    category_id: null,
    decision_version: 0,
  };
  vi.mocked(readPage).mockResolvedValue({ rows: [row], total: 1 });
  const rpc = vi
    .fn()
    .mockResolvedValueOnce({
      data: { account_id: "pot", category_id: null, version: 1 },
      error: null,
    })
    .mockResolvedValueOnce({
      data: { account_id: "pot", category_id: "food", version: 2 },
      error: null,
    })
    .mockResolvedValueOnce({ data: null, error: { code: "PT409" } });
  render(
    <Workspace
      api={{ rpc } as unknown as BrowserClient}
      owner="Owner"
      initialRange={["2026-01-01", "2026-01-31"]}
      onExit={() => {}}
    />,
  );
  const account = (await screen.findByLabelText(
    `Account for ${row.description}`,
  )) as HTMLSelectElement;
  const originalRow = account.closest("tr");
  await user.selectOptions(account, "pot");
  await waitFor(() => expect(account.value).toBe("pot"));
  const category = screen.getByLabelText(
    `Category for ${row.description}`,
  ) as HTMLSelectElement;
  await user.selectOptions(category, "food");
  await waitFor(() => expect(category.value).toBe("food"));
  expect(rpc.mock.calls[1][1].p_expected_version).toBe(1);
  expect(readPage).toHaveBeenCalledTimes(1);
  expect(category.closest("tr")).toBe(originalRow);
  expect(document.activeElement).toBe(category);
  await user.selectOptions(account, "");
  expect((await screen.findByRole("alert")).textContent).toContain(
    "This entry changed",
  );
  expect(account.value).toBe("pot");
  expect(category.value).toBe("food");
  expect(readPage).toHaveBeenCalledTimes(1);
});

it("resets pagination when changing date sort and preserves the selected direction across pages", async () => {
  const user = userEvent.setup();
  vi.mocked(readPage).mockResolvedValue({ rows: [demoEntries[0]], total: 101 });
  render(
    <Workspace
      api={{} as BrowserClient}
      owner="Owner"
      initialRange={["2026-01-01", "2026-01-31"]}
      onExit={() => {}}
    />,
  );
  await screen.findByText(demoEntries[0].description);
  await user.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() => expect(vi.mocked(readPage).mock.lastCall?.[4]).toBe(50));
  await user.selectOptions(
    screen.getByLabelText("Sort by transaction date"),
    "oldest",
  );
  await waitFor(() => {
    expect(vi.mocked(readPage).mock.lastCall?.[4]).toBe(0);
    expect(vi.mocked(readPage).mock.lastCall?.[7]).toBe("oldest");
  });
  await user.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() => {
    expect(vi.mocked(readPage).mock.lastCall?.[4]).toBe(50);
    expect(vi.mocked(readPage).mock.lastCall?.[7]).toBe("oldest");
  });
});

it.each(["Statement date", "Transaction date"])(
  "browses full months in the %s view, resetting pagination and handling leap years and year boundaries",
  async (viewName) => {
    const user = userEvent.setup();
    vi.mocked(readPage).mockResolvedValue({
      rows: [demoEntries[0]],
      total: 101,
    });
    render(
      <Workspace
        api={{} as BrowserClient}
        owner="Owner"
        initialRange={["2024-03-31", "2024-03-31"]}
        onExit={() => {}}
      />,
    );
    await screen.findByText(demoEntries[0].description);
    await user.click(screen.getByRole("tab", { name: viewName }));
    await user.click(screen.getByRole("button", { name: /^Next$/ }));
    await waitFor(() =>
      expect(vi.mocked(readPage).mock.lastCall?.[4]).toBe(50),
    );
    await user.click(screen.getByRole("button", { name: "Previous month" }));
    await waitFor(() => {
      const call = vi.mocked(readPage).mock.lastCall!;
      expect(call.slice(1, 5)).toEqual([
        viewName === "Statement date" ? "statement" : "transaction",
        "2024-02-01",
        "2024-02-29",
        0,
      ]);
    });
    expect(screen.getByText("February 2024")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Next month" }));
    await waitFor(() =>
      expect(vi.mocked(readPage).mock.lastCall?.slice(2, 4)).toEqual([
        "2024-03-01",
        "2024-03-31",
      ]),
    );
    for (let i = 0; i < 3; i++)
      await user.click(screen.getByRole("button", { name: "Previous month" }));
    await waitFor(() =>
      expect(vi.mocked(readPage).mock.lastCall?.slice(2, 4)).toEqual([
        "2023-12-01",
        "2023-12-31",
      ]),
    );
    await user.click(screen.getByRole("button", { name: "Next month" }));
    await waitFor(() =>
      expect(vi.mocked(readPage).mock.lastCall?.slice(2, 4)).toEqual([
        "2024-01-01",
        "2024-01-31",
      ]),
    );
    await user.click(screen.getByRole("tab", { name: "Needs review" }));
    expect(screen.queryByRole("group", { name: "Browse months" })).toBeNull();
  },
);
