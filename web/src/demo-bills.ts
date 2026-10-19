import type { Entry } from "./domain";
import type { StatementBill } from "./statement-bills";

// Explicitly invented printed balances, independent of the spend calculator.
const balances: Record<string, [string, string, string, string]> = {
  "demo-import-1-2026-01-31-true": ["5000.00", "5000.00", "840.00", "840.00"],
  "demo-import-2-2026-01-31-true": ["0.00", "0.00", "368.10", "368.00"],
  "demo-import-3-2026-01-31-true": ["100.00", "125.50", "2450.75", "2425.00"],
  "demo-import-4-2026-01-31-true": ["0.00", "0.00", "299.00", "299.00"],
};
export function demoStatementBills(rows: Entry[]): StatementBill[] {
  const selected = new Map(
    rows.filter((row) => row.is_selected).map((row) => [row.import_id, row]),
  );
  return [...selected.values()].map((row) => {
    const values = balances[row.import_id];
    return {
      id: row.import_id,
      statement_id: row.statement_id,
      card_id: row.card_id ?? row.card_label,
      card_label: row.card_label,
      bank: row.bank,
      statement_date:
        row.effective_statement_date === undefined
          ? row.statement_date
          : row.effective_statement_date,
      printed_statement_date: row.printed_statement_date ?? row.statement_date,
      printed_balance: values
        ? {
            currency: "INR",
            previous_balance: values[0],
            payments_and_credits: values[1],
            charges: values[2],
            finance_charges: "0.00",
            amount_due: values[3],
            source: { page: 1 },
          }
        : null,
    };
  });
}
