// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
afterEach(cleanup);
async function setup() {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  );
  await user.click(screen.getByRole("button", { name: "Accounts" }));
  await user.type(screen.getByLabelText("Account name"), "Synthetic pot");
  await user.click(screen.getByRole("button", { name: "Create Account" }));
  await user.click(screen.getByRole("button", { name: "Statements" }));
  await user.click(screen.getByRole("tab", { name: "Transaction date" }));
  for (const name of ["Streaming subscription", "Late-posted train ticket"]) {
    await user.click(
      screen.getByRole("button", { name: "Details for " + name }),
    );
    await user.click(screen.getByRole("button", { name: "Edit entry" }));
    await user.selectOptions(
      screen.getByLabelText("Account", { exact: true }),
      within(screen.getByLabelText("Account", { exact: true })).getByRole(
        "option",
        { name: "Synthetic pot" },
      ),
    );
    await user.click(screen.getByRole("button", { name: "Save assignments" }));
  }
  await user.click(screen.getByRole("button", { name: "Reconciliation" }));
  return user;
}
it("records partial/full contributions and keeps arrears in January when paid in February", async () => {
  const user = await setup();
  await user.click(
    screen.getByRole("button", { name: "View cards for Synthetic pot (INR)" }),
  );
  await user.click(
    screen.getByRole("button", {
      name: "Contributions for YES Bank • demo · 2026-01",
    }),
  );
  let detail = within(
    screen.getByRole("region", { name: "Contributions and balances" }),
  );
  await user.type(detail.getByLabelText("Partial contribution amount"), "100");
  await user.click(
    detail.getByRole("button", { name: "Record partial contribution" }),
  );
  expect(detail.getByText("Outstanding: INR 199.00")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Reconciliation month"), {
    target: { value: "02" },
  });
  await user.click(
    screen.getByRole("button", { name: "View cards for Synthetic pot (INR)" }),
  );
  await user.click(
    screen.getByRole("button", {
      name: "Contributions for YES Bank • demo · 2026-02",
    }),
  );
  detail = within(
    screen.getByRole("region", { name: "Contributions and balances" }),
  );
  expect(detail.getByText("Outstanding: INR 1,119.00")).toBeTruthy();
  await user.type(detail.getByLabelText("Partial contribution amount"), "250");
  await user.click(
    detail.getByRole("button", { name: "Record partial contribution" }),
  );
  expect(detail.getByText("2026-01: INR 199.00")).toBeTruthy();
  expect(detail.getByText("2026-02: INR 51.00")).toBeTruthy();
  expect(detail.getByText("Outstanding: INR 869.00")).toBeTruthy();
  await user.click(detail.getByRole("button", { name: "Settle in full" }));
  expect(detail.getByText("Outstanding: INR 0.00")).toBeTruthy();
  expect(detail.getAllByText("Settled")).toHaveLength(2);
  await user.click(screen.getByRole("button", { name: "Statements" }));
  await user.click(screen.getByRole("button", { name: "Reconciliation" }));
  await user.click(
    screen.getByRole("button", { name: "View cards for Synthetic pot (INR)" }),
  );
  await user.click(
    screen.getByRole("button", {
      name: "Contributions for YES Bank • demo · 2026-02",
    }),
  );
  expect(screen.getByText("2026-01: INR 199.00")).toBeTruthy();
});
it("shows included entries and blocks unassigned groups without blocking a ready card", async () => {
  const user = await setup();
  expect(
    screen.getByRole("button", { name: "View cards for Unassigned (INR)" }),
  ).toBeTruthy();
  await user.click(
    screen.getByRole("button", { name: "View cards for Synthetic pot (INR)" }),
  );
  await user.click(screen.getByText("Included entries · 2026-01"));
  const entries = within(
    await screen.findByRole("list", { name: "Included entries" }),
  );
  expect(await entries.findByText("Streaming subscription")).toBeTruthy();
  expect(entries.getByText("18 Jan 2026")).toBeTruthy();
  expect(entries.getByText("purchase")).toBeTruthy();
  expect(entries.getByText("− INR 299.00")).toBeTruthy();
  await user.click(
    screen.getByRole("button", {
      name: "Contributions for YES Bank • demo · 2026-01",
    }),
  );
  expect(
    (
      screen.getByRole("button", {
        name: "Settle in full",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(false);
});

it("selects a reconciliation month and year without native month input support", async () => {
  const user = await setup();
  const month = screen.getByRole("combobox", { name: "Reconciliation month" });
  const year = screen.getByRole("spinbutton", { name: "Reconciliation year" });
  await user.selectOptions(month, "12");
  expect(screen.getByText("Account summary · 2026-12")).toBeTruthy();
  await user.clear(year);
  await user.type(year, "2025");
  expect(screen.getByText("Account summary · 2025-12")).toBeTruthy();
  await user.clear(year);
  await user.type(year, "0000");
  await user.tab();
  expect((year as HTMLInputElement).value).toBe("2025");
  expect(screen.getByText("Account summary · 2025-12")).toBeTruthy();
});
