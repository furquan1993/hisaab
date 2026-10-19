import { z } from "zod";
import type { BrowserClient } from "./client";
import { cents } from "./funding-domain";

const amount = z.string().regex(/^\d+\.\d{2}$/);
export const printedBalanceSchema = z.object({
  currency: z.string().regex(/^[A-Z]{3}$/),
  previous_balance: amount,
  payments_and_credits: amount,
  charges: amount,
  finance_charges: amount,
  amount_due: amount,
  source: z.object({ page: z.number().int().positive() }),
});
export const statementBillSchema = z.object({
  id: z.string(),
  statement_id: z.string(),
  card_id: z.string(),
  card_label: z.string(),
  bank: z.string(),
  statement_date: z.string().nullable(),
  printed_statement_date: z.string().nullable(),
  printed_balance: printedBalanceSchema.nullable(),
});
export type StatementBill = z.infer<typeof statementBillSchema>;

export async function readStatementBills(
  api: BrowserClient,
  start: string,
  end: string,
  signal: AbortSignal,
) {
  const bills: StatementBill[] = [];
  for (let offset = 0; ; offset += 100) {
    const { data, error } = await api
      .from("statement_bills")
      .select("*")
      .gte("statement_date", start)
      .lte("statement_date", end)
      .order("card_id")
      .order("statement_date")
      .order("id")
      .range(offset, offset + 99)
      .abortSignal(signal);
    if (error)
      throw new Error(
        "Printed bill balances could not be loaded. Reload to retry. Spending is shown separately below.",
      );
    const page = z.array(statementBillSchema).parse(data);
    bills.push(...page);
    if (page.length < 100) return bills;
  }
}

export function billArithmetic(
  balance: NonNullable<StatementBill["printed_balance"]>,
) {
  const calculated =
    cents(balance.previous_balance) +
    cents(balance.charges) +
    cents(balance.finance_charges) -
    cents(balance.payments_and_credits);
  return { calculated, difference: cents(balance.amount_due) - calculated };
}
