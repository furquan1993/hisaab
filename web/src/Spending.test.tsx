// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import Spending from "./Spending";
import { demoEntries } from "./demo";
import type { SpendingStore } from "./useSpending";
afterEach(cleanup);

it("preserves the requested currency when opening category spending", () => {
  const base = {
    ...demoEntries[0],
    is_selected: true,
    needs_review: false,
    group_id: null,
    group_name: null,
    group_version: 0,
  };
  const store: SpendingStore = {
    rows: [
      { ...base, id: "inr", currency: "INR", amount: "840.00" },
      { ...base, id: "usd", currency: "USD", amount: "12.34" },
    ],
    groups: [],
    loading: false,
    error: "",
    busy: false,
    reload: vi.fn(),
    saveGroup: vi.fn(),
    assign: vi.fn(),
  };
  render(
    <Spending
      store={store}
      labels={[]}
      demo={false}
      initialFocus={{
        view: "category",
        id: "uncategorized",
        period: "all",
        currency: "USD",
      }}
      onCategories={vi.fn()}
    />,
  );
  expect(
    (screen.getByLabelText("Spending currency") as HTMLSelectElement).value,
  ).toBe("USD");
  expect(
    screen.getByText("USD 12.34", { selector: ".spending-net" }),
  ).toBeTruthy();
  expect(
    screen.queryByText("INR 840.00", { selector: ".spending-net" }),
  ).toBeNull();
});

it("creates a trip, groups expenses across cards, filters its categories, and edits membership from Statements", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  );
  await user.click(screen.getByRole("button", { name: "Spending" }));
  expect(screen.queryByText("Payment received")).toBeNull();
  await user.click(screen.getByRole("button", { name: "+ New group" }));
  await user.type(screen.getByLabelText("Group name"), "Goa trip");
  await user.click(screen.getByRole("button", { name: "Create group" }));
  await user.click(screen.getByRole("button", { name: "Add / move entries" }));
  await user.click(
    screen.getByRole("checkbox", { name: "Select Streaming subscription" }),
  );
  await user.click(
    screen.getByRole("checkbox", { name: "Select Late-posted train ticket" }),
  );
  await user.click(screen.getByRole("button", { name: "Save 2 assignments" }));
  let detail = within(
    screen.getByRole("region", { name: "Selected spending" }),
  );
  expect(
    detail.getByText("INR 1,219.00", { selector: ".spending-net" }),
  ).toBeTruthy();
  expect(detail.getByText("Streaming subscription")).toBeTruthy();
  expect(detail.getByText("Late-posted train ticket")).toBeTruthy();
  await user.click(detail.getByRole("button", { name: /^Uncategorized/ }));
  expect(detail.getByRole("button", { name: "Clear filter" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Statements" }));
  await user.click(
    screen.getByRole("button", { name: "Details for Streaming subscription" }),
  );
  await user.click(
    screen.getByRole("button", { name: "Assign trip or group" }),
  );
  expect(
    (screen.getByLabelText("Entry trip or group") as HTMLSelectElement)
      .selectedOptions[0].text,
  ).toBe("Goa trip");
  await user.selectOptions(screen.getByLabelText("Entry trip or group"), "");
  await user.click(
    screen.getByRole("button", { name: "Save trip assignment" }),
  );
  await user.click(screen.getByRole("button", { name: "Spending" }));
  detail = within(screen.getByRole("region", { name: "Selected spending" }));
  expect(
    detail.getByText("INR 920.00", { selector: ".spending-net" }),
  ).toBeTruthy();
  expect(detail.queryByText("Streaming subscription")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Manage group" }));
  await user.clear(screen.getByLabelText("Group name"));
  await user.type(screen.getByLabelText("Group name"), "Goa holiday");
  await user.click(screen.getByRole("button", { name: "Save group" }));
  expect(screen.getByRole("heading", { name: "Goa holiday" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "By category" }));
  expect(screen.getByRole("heading", { name: "Uncategorized" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Reconciliation" }));
  expect(
    screen.getByRole("button", { name: "View cards for Unassigned (INR)" }),
  ).toBeTruthy();
});

it("opens a category from Summary with an explicit transaction-date period", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  );
  await user.click(screen.getByRole("button", { name: "Summary" }));
  await user.selectOptions(screen.getByLabelText("Date basis"), "transaction");
  await user.click(
    screen.getByRole("button", { name: "Explore Unassigned spending" }),
  );
  expect(
    (screen.getByLabelText("Spending period") as HTMLSelectElement).value,
  ).toBe("2026-01");
  expect(
    screen.getByRole("heading", { name: "Uncategorized", level: 2 }),
  ).toBeTruthy();
});
