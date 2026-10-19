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
it("places search, filters and sorting in their table column headers", async () => {
  const user = userEvent.setup();
  vi.mocked(readPage).mockResolvedValue({ rows: [demoEntries[0]], total: 1 });
  render(
    <Workspace
      api={{} as BrowserClient}
      owner="Owner"
      initialRange={["2026-01-01", "2026-01-31"]}
      onExit={() => {}}
    />,
  );
  await screen.findByText(demoEntries[0].description);
  for (const [name, column] of [
    ["Search descriptions", "Transaction"],
    ["Filter by account", "Account"],
    ["Filter by category", "Category"],
    ["Sort by transaction date", "Date"],
    ["Filter dates", "Date"],
    ["From", "Date"],
    ["To", "Date"],
  ]) {
    expect(
      screen.getByLabelText(name, { exact: true }).closest("th")?.textContent,
    ).toContain(column);
  }
  const dateHeader = screen
    .getByLabelText("Sort by transaction date")
    .closest("th")!;
  expect(dateHeader.getAttribute("aria-sort")).toBe("descending");
  await user.selectOptions(
    screen.getByLabelText("Sort by transaction date"),
    "oldest",
  );
  expect(dateHeader.getAttribute("aria-sort")).toBe("ascending");
  expect(
    document.querySelector(
      ".statement-filters input, .statement-filters select",
    ),
  ).toBeNull();
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

it("keeps a friendly-description draft on conflict and saves without changing assignments or decision version", async () => {
  const user = userEvent.setup();
  const row = {
    ...demoEntries[0],
    account_id: "pot",
    category_id: "food",
    decision_version: 7,
  };
  vi.mocked(readPage).mockResolvedValue({ rows: [row], total: 1 });
  const rpc = vi
    .fn()
    .mockResolvedValueOnce({ data: null, error: { code: "PT409" } })
    .mockResolvedValueOnce({
      data: {
        friendly_description: "Amazon desk lamp",
        friendly_description_version: 1,
      },
      error: null,
    })
    .mockResolvedValueOnce({
      data: { account_id: "pot", category_id: null, version: 8 },
      error: null,
    });
  render(
    <Workspace
      api={{ rpc } as unknown as BrowserClient}
      owner="Owner"
      initialRange={["2026-01-01", "2026-01-31"]}
      onExit={() => {}}
    />,
  );
  await user.click(
    await screen.findByRole("button", {
      name: `Details for ${row.description}`,
    }),
  );
  await user.click(screen.getByRole("button", { name: "Edit description" }));
  const input = screen.getByLabelText("Friendly description", { exact: true });
  await user.type(input, "Amazon desk lamp");
  await user.click(screen.getByRole("button", { name: "Save description" }));
  expect((await screen.findByRole("alert")).textContent).toContain(
    "Your draft is kept",
  );
  expect((input as HTMLInputElement).value).toBe("Amazon desk lamp");
  await user.click(screen.getByRole("button", { name: "Save description" }));
  await screen.findByText("Amazon desk lamp");
  expect(screen.getByText(`Statement: ${row.description}`)).toBeTruthy();
  expect(
    (
      screen.getByLabelText(
        `Account for ${row.description}`,
      ) as HTMLSelectElement
    ).value,
  ).toBe("pot");
  await user.selectOptions(
    screen.getByLabelText(`Category for ${row.description}`),
    "",
  );
  await waitFor(() => expect(rpc).toHaveBeenCalledTimes(3));
  expect(rpc.mock.calls[2][1].p_expected_version).toBe(7);
  expect(rpc.mock.calls[0][0]).toBe("save_friendly_description");
  expect(rpc.mock.calls[0][1].p_expected_version).toBe(0);
});

it("passes description searches to the paginated API and resets to the first page", async () => {
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
  await user.type(screen.getByLabelText("Search descriptions"), "Amazon");
  await waitFor(() => {
    expect(vi.mocked(readPage).mock.lastCall?.[4]).toBe(0);
    expect(vi.mocked(readPage).mock.lastCall?.[8]).toBe("Amazon");
  });
});

it("combines account and category filters with search and resets pagination", async () => {
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
  await user.selectOptions(screen.getByLabelText("Filter by account"), "pot");
  await user.selectOptions(screen.getByLabelText("Filter by category"), "food");
  await user.type(screen.getByLabelText("Search descriptions"), "train");
  await waitFor(() => {
    const call = vi.mocked(readPage).mock.lastCall;
    expect(call?.[4]).toBe(0);
    expect(call?.[8]).toBe("train");
    expect(call?.[9]).toEqual({ accountId: "pot", categoryId: "food" });
  });
  await user.selectOptions(
    screen.getByLabelText("Filter by account"),
    "unassigned",
  );
  await user.selectOptions(screen.getByLabelText("Filter by category"), "");
  await waitFor(() =>
    expect(vi.mocked(readPage).mock.lastCall?.[9]).toEqual({
      accountId: null,
      categoryId: undefined,
    }),
  );
});

it("filters demo transactions by assignments and description together", async () => {
  const user = userEvent.setup();
  render(
    <Workspace
      api={null}
      owner="Demo"
      initialRange={["2026-01-01", "2026-01-31"]}
      onExit={() => {}}
    />,
  );
  const description = demoEntries.find(
    (r) => r.is_selected && r.statement_date?.startsWith("2026-01"),
  )!.description;
  await user.type(screen.getByLabelText("Search descriptions"), description);
  const account = await screen.findByLabelText(`Account for ${description}`);
  await user.selectOptions(account, "pot");
  await user.selectOptions(screen.getByLabelText("Filter by account"), "pot");
  await screen.findByLabelText(`Account for ${description}`);
  await user.selectOptions(screen.getByLabelText("Filter by category"), "food");
  await waitFor(() =>
    expect(screen.queryByLabelText(`Account for ${description}`)).toBeNull(),
  );
  await user.selectOptions(
    screen.getByLabelText("Filter by category"),
    "unassigned",
  );
  const reassigned = await screen.findByLabelText(`Account for ${description}`);
  await user.selectOptions(reassigned, "");
  await waitFor(() =>
    expect(screen.queryByLabelText(`Account for ${description}`)).toBeNull(),
  );
});

it("bulk updates account then category without changing the other assignment", async () => {
  const user = userEvent.setup();
  const rows = [0, 1].map((i) => ({
    ...demoEntries[0],
    id: `bulk-${i}`,
    description: `Bulk expense ${i}`,
    is_selected: true,
    account_id: null,
    category_id: null,
  }));
  vi.mocked(readPage).mockResolvedValue({ rows, total: 2 });
  const rpc = vi
    .fn()
    .mockResolvedValueOnce({
      data: { account_id: "pot", category_id: null, version: 1 },
      error: null,
    })
    .mockResolvedValueOnce({
      data: { account_id: "pot", category_id: null, version: 1 },
      error: null,
    })
    .mockResolvedValue({
      data: { account_id: "pot", category_id: "food", version: 2 },
      error: null,
    });
  render(
    <Workspace
      api={{ rpc } as unknown as BrowserClient}
      owner="Owner"
      initialRange={["2026-01-01", "2026-01-31"]}
      onExit={() => {}}
    />,
  );
  await screen.findByText("Bulk expense 0");
  await user.click(
    screen.getByRole("button", { name: "Select all on this page" }),
  );
  expect(screen.queryByRole("button", { name: "Edit entry" })).toBeNull();
  await user.selectOptions(
    screen.getByLabelText("Account for selected transactions"),
    "pot",
  );
  await user.click(screen.getByRole("button", { name: "Set account" }));
  await screen.findByText(
    "2 of 2 transactions updated. Categories and trips unchanged.",
  );
  expect(
    (screen.getByLabelText("Account for Bulk expense 0") as HTMLSelectElement)
      .value,
  ).toBe("pot");
  await user.click(screen.getByLabelText("Select transaction Bulk expense 0"));
  await user.selectOptions(
    screen.getByLabelText("Category for selected transactions"),
    "food",
  );
  await user.click(screen.getByRole("button", { name: "Set category" }));
  await screen.findByText(
    "1 of 1 transactions updated. Accounts and trips unchanged.",
  );
  expect(rpc.mock.calls[2][1]).toEqual({
    p_entry_id: "bulk-0",
    p_expected_version: 1,
    p_patch: { category_id: "food" },
  });
  expect(
    (screen.getByLabelText("Account for Bulk expense 0") as HTMLSelectElement)
      .value,
  ).toBe("pot");
  expect(
    (screen.getByLabelText("Category for Bulk expense 1") as HTMLSelectElement)
      .value,
  ).toBe("");
});

it("clears bulk selection when filtering and reports a partially saved batch", async () => {
  const user = userEvent.setup();
  const rows = [0, 1, 2].map((i) => ({
    ...demoEntries[0],
    id: `partial-${i}`,
    description: `Partial ${i}`,
    is_selected: i !== 2,
    account_id: null,
    category_id: null,
  }));
  vi.mocked(readPage).mockResolvedValue({ rows, total: 3 });
  const rpc = vi
    .fn()
    .mockResolvedValueOnce({
      data: { account_id: "pot", category_id: null, version: 1 },
      error: null,
    })
    .mockResolvedValueOnce({ error: { code: "PT409" } });
  render(
    <Workspace
      api={{ rpc } as unknown as BrowserClient}
      owner="Owner"
      initialRange={["2026-01-01", "2026-01-31"]}
      onExit={() => {}}
    />,
  );
  await screen.findByText("Partial 0");
  expect(
    (screen.getByLabelText("Select transaction Partial 2") as HTMLInputElement)
      .disabled,
  ).toBe(true);
  await user.click(
    screen.getByRole("button", { name: "Select all on this page" }),
  );
  expect(screen.getByText("2 selected on this page")).toBeTruthy();
  await user.selectOptions(
    screen.getByLabelText("Filter by category"),
    "unassigned",
  );
  await screen.findByText("0 selected on this page");
  await user.click(
    screen.getByRole("button", { name: "Select all on this page" }),
  );
  await user.selectOptions(
    screen.getByLabelText("Account for selected transactions"),
    "pot",
  );
  await user.click(screen.getByRole("button", { name: "Set account" }));
  await screen.findByText(
    "1 of 2 transactions updated. Categories and trips unchanged.",
  );
  expect((await screen.findByRole("alert")).textContent).toContain(
    "batch stopped",
  );
  expect(rpc).toHaveBeenCalledTimes(2);
});
