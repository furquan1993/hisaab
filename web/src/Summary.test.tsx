// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import Summary from "./Summary";
import { demoEntries } from "./demo";
import { readSummary } from "./summary-client";
import type { BrowserClient } from "./client";
import type { Entry } from "./domain";
vi.mock("./summary-client", () => ({ readSummary: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
const row = (changes: Partial<Entry> = {}): Entry => ({
  ...demoEntries[0],
  amount: "100.00",
  direction: "debit",
  is_selected: true,
  entry_type: "purchase",
  needs_review: false,
  statement_date: "2026-01-31",
  transaction_date: "2025-12-30",
  ...changes,
});
function setup(api: BrowserClient | null = null, rows = [row()]) {
  const onEntries = vi.fn(),
    onImports = vi.fn(),
    onReconciliation = vi.fn();
  function Harness() {
    const [month, setMonth] = useState("2026-01");
    return (
      <Summary
        api={api}
        month={month}
        onMonth={setMonth}
        demoRows={rows}
        labels={[]}
        onEntries={onEntries}
        onImports={onImports}
        onReconciliation={onReconciliation}
      />
    );
  }
  render(<Harness />);
  return { user: userEvent.setup(), onEntries, onImports, onReconciliation };
}
it("shows exact spend without repayments and routes to entries in the chosen month and date basis", async () => {
  const { user, onEntries, onReconciliation } = setup(null, [
    row(),
    row({ entry_type: "payment", amount: "1000.00", direction: "credit" }),
    row({ entry_type: "refund", amount: "10.25", direction: "credit" }),
  ]);
  const summary = within(
    screen.getByRole("region", { name: "INR spending summary" }),
  );
  expect(summary.getAllByText("INR 89.75")).toHaveLength(4);
  expect(summary.getByText("INR 100.00")).toBeTruthy();
  expect(summary.getByText("INR 10.25")).toBeTruthy();
  expect(screen.getByText(/1 card payment excluded/)).toBeTruthy();
  await user.selectOptions(screen.getByLabelText("Date basis"), "transaction");
  expect(screen.getByText("No spending entries this month")).toBeTruthy();
  await user.click(
    screen.getByRole("button", { name: "Previous summary month" }),
  );
  expect(screen.getByText("December 2025")).toBeTruthy();
  expect(
    screen.getByRole("region", { name: "INR spending summary" }),
  ).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "View entries" }));
  expect(onEntries).toHaveBeenCalledWith("transaction");
  await user.click(screen.getByRole("button", { name: "View reconciliation" }));
  expect(onReconciliation).toHaveBeenCalledOnce();
});

it("flags missing dates and amounts, shows separate currencies and keeps negative totals", () => {
  setup(null, [
    row({ effective_amount: null, needs_review: true }),
    row({ effective_statement_date: null }),
    row({
      currency: "USD",
      direction: "credit",
      entry_type: "refund",
      amount: "5.00",
    }),
  ]);
  expect(screen.getByRole("status").textContent).toContain(
    "1 entry is excluded",
  );
  expect(screen.getByRole("status").textContent).toContain(
    "1 selected entry across all imports",
  );
  expect(
    within(
      screen.getByRole("region", { name: "USD spending summary" }),
    ).getAllByText("− USD 5.00"),
  ).toHaveLength(4);
  expect(
    screen.queryByRole("region", { name: "INR spending summary" }),
  ).toBeNull();
});

it("discards an obsolete month's response and hides previous totals while loading or after failure", async () => {
  let resolveOld!: (result: Awaited<ReturnType<typeof readSummary>>) => void;
  vi.mocked(readSummary)
    .mockReturnValueOnce(
      new Promise((resolve) => {
        resolveOld = resolve;
      }),
    )
    .mockResolvedValueOnce({
      rows: [row({ amount: "200.00" })],
      undated: 0,
      bills: [],
      billsError: "",
    })
    .mockRejectedValueOnce(Error("Could not load summary"));
  const { user } = setup({} as BrowserClient);
  expect(screen.getByRole("status").textContent).toContain("Loading");
  await user.click(screen.getByRole("button", { name: "Next summary month" }));
  await screen.findAllByText("INR 200.00");
  resolveOld({
    rows: [row({ amount: "999.00" })],
    undated: 0,
    bills: [],
    billsError: "",
  });
  await waitFor(() =>
    expect(vi.mocked(readSummary).mock.calls[0][3].aborted).toBe(true),
  );
  expect(screen.queryByText("INR 999.00")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Reload summary" }));
  expect((await screen.findByRole("alert")).textContent).toContain(
    "Could not load summary",
  );
  expect(screen.queryByText("INR 200.00")).toBeNull();
  vi.mocked(readSummary).mockResolvedValueOnce({
    rows: [],
    undated: 0,
    bills: [],
    billsError: "",
  });
  await user.click(screen.getByRole("button", { name: "Reload summary" }));
  expect(
    await screen.findByText("No spending entries this month"),
  ).toBeTruthy();
});
