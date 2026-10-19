// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StatementBills from "./StatementBills";
import { billArithmetic, type StatementBill } from "./statement-bills";

afterEach(cleanup);
const bill: StatementBill = {
  id: "import",
  statement_id: "statement",
  card_id: "card",
  card_label: "Invented card",
  bank: "hdfc",
  statement_date: "2026-09-13",
  printed_statement_date: "2026-09-13",
  printed_balance: {
    currency: "INR",
    previous_balance: "4654.57",
    payments_and_credits: "7021.41",
    charges: "7582.14",
    finance_charges: "0.00",
    amount_due: "5215.00",
    source: { page: 1 },
  },
};
it("shows the printed due and exact bill arithmetic, including an unexplained difference", async () => {
  expect(billArithmetic(bill.printed_balance!)).toEqual({
    calculated: 521530n,
    difference: -30n,
  });
  render(<StatementBills bills={[bill]} error="" />);
  expect(screen.getByText("INR 5,215.00")).toBeTruthy();
  await userEvent.setup().click(screen.getByText("How this bill adds up"));
  expect(screen.getByText("INR 5,215.30")).toBeTruthy();
  expect(screen.getByText("− INR 0.30")).toBeTruthy();
  expect(
    screen.getByText(/may apply rounding or another adjustment/),
  ).toBeTruthy();
});
it("does not invent an amount due when the printed balance is missing", () => {
  render(
    <StatementBills bills={[{ ...bill, printed_balance: null }]} error="" />,
  );
  expect(screen.getByText("Not captured")).toBeTruthy();
  expect(screen.queryByText("How this bill adds up")).toBeNull();
});
it("shows missing bill data as a separate status without guessing from spend", () => {
  render(
    <StatementBills
      bills={[]}
      error="Printed bill balances could not be loaded."
    />,
  );
  expect(screen.getByRole("status").textContent).toContain(
    "could not be loaded",
  );
});
