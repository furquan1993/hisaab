import { decimalText, fundingMoney } from "./funding-domain";
import { billArithmetic, type StatementBill } from "./statement-bills";

export default function StatementBills({
  bills,
  error,
}: {
  bills: StatementBill[];
  error: string;
}) {
  return (
    <section className="statement-bills" aria-label="Statement bills">
      <h2>Statement bills</h2>
      <p className="summary-method">
        The printed amount due includes the previous balance and payments
        received. It can differ from spending in this billing cycle.
      </p>
      {error ? (
        <p role="status" className="notice">
          {error}
        </p>
      ) : !bills.length ? (
        <p>
          No selected statements in this month. Check Imports for statement
          coverage.
        </p>
      ) : (
        <div className="summary-grid">
          {bills.map((bill) => {
            const balance = bill.printed_balance;
            const totals = balance ? billArithmetic(balance) : null;
            const money = (value: string) =>
              fundingMoney(value, balance?.currency ?? null);
            return (
              <article className="ledger statement-bill" key={bill.id}>
                <h3>{bill.card_label}</h3>
                <p className="bill-date">
                  Statement date: {bill.printed_statement_date ?? "Unknown"}
                </p>
                <dl className="bill-amount">
                  <dt>Statement amount due</dt>
                  <dd>
                    {balance ? money(balance.amount_due) : "Not captured"}
                  </dd>
                </dl>
                {balance && totals ? (
                  <details>
                    <summary>How this bill adds up</summary>
                    <dl className="bill-breakdown">
                      <div>
                        <dt>Previous statement balance</dt>
                        <dd>{money(balance.previous_balance)}</dd>
                      </div>
                      <div>
                        <dt>Payments and credits received</dt>
                        <dd>− {money(balance.payments_and_credits)}</dd>
                      </div>
                      <div>
                        <dt>This cycle’s charges</dt>
                        <dd>{money(balance.charges)}</dd>
                      </div>
                      <div>
                        <dt>Finance charges</dt>
                        <dd>{money(balance.finance_charges)}</dd>
                      </div>
                      <div>
                        <dt>Calculated amount due</dt>
                        <dd>{money(decimalText(totals.calculated))}</dd>
                      </div>
                      {totals.difference !== 0n && (
                        <div>
                          <dt>Difference from printed bill</dt>
                          <dd>{money(decimalText(totals.difference))}</dd>
                        </div>
                      )}
                    </dl>
                    {totals.difference !== 0n && (
                      <p className="bill-note">
                        The printed bill differs from the calculation above. The
                        bank may apply rounding or another adjustment; the
                        amount due is shown exactly as printed.
                      </p>
                    )}
                    <p className="bill-note">
                      Source: statement page {balance.source.page}. These are
                      printed bill figures; contributions are tracked
                      separately.
                    </p>
                  </details>
                ) : (
                  <p className="bill-note">
                    The printed balance has not been captured for this import.
                    Spending below does not include any previous balance.
                  </p>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
