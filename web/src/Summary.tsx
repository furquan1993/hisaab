import { useEffect, useState } from "react";
import type { BrowserClient } from "./client";
import { filterEntries, monthRange, type Entry } from "./domain";
import { decimalText, fundingMoney } from "./funding-domain";
import { readSummary, type SummaryBasis } from "./summary-client";
import {
  sortedBuckets,
  summarizeSpend,
  type SpendBucket,
} from "./summary-domain";
import type { Label } from "./useLabels";
import StatementBills from "./StatementBills";
import type { StatementBill } from "./statement-bills";
import { demoStatementBills } from "./demo-bills";

const money = (amount: bigint, currency: string) =>
  fundingMoney(decimalText(amount), currency);

function Breakdown({
  title,
  currency,
  buckets,
  onBucket,
}: {
  title: string;
  currency: string;
  buckets: Map<string, SpendBucket>;
  onBucket?: (id: string) => void;
}) {
  return (
    <section className="ledger summary-breakdown">
      <div className="table-scroll">
        <table>
          <caption>
            {title} · {currency}
          </caption>
          <thead>
            <tr>
              <th scope="col">{title}</th>
              <th scope="col">Entries</th>
              <th scope="col">Net spend</th>
            </tr>
          </thead>
          <tbody>
            {sortedBuckets(buckets).map((bucket) => (
              <tr key={bucket.id}>
                <th scope="row">
                  {onBucket ? (
                    <button
                      type="button"
                      className="summary-category-link"
                      onClick={() => onBucket(bucket.id)}
                      aria-label={`Explore ${bucket.name} spending`}
                    >
                      {bucket.name}
                    </button>
                  ) : (
                    bucket.name
                  )}
                </th>
                <td>{bucket.count}</td>
                <td>{money(bucket.charges - bucket.credits, currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function Summary({
  api,
  month,
  onMonth,
  demoRows,
  labels,
  onEntries,
  onImports,
  onReconciliation,
  onSpending,
}: {
  api: BrowserClient | null;
  month: string;
  onMonth: (month: string) => void;
  demoRows: Entry[];
  labels: Label[];
  onEntries: (basis: SummaryBasis) => void;
  onImports: () => void;
  onReconciliation: () => void;
  onSpending?: (categoryId: string, period: string, currency: string) => void;
}) {
  const [basis, setBasis] = useState<SummaryBasis>("statement");
  const [refresh, setRefresh] = useState(0);
  const [loaded, setLoaded] = useState<{
    key: string;
    rows: Entry[];
    undated: number;
    bills?: StatementBill[];
    billsError?: string;
  } | null>(null);
  const [error, setError] = useState<{ key: string; message: string } | null>(
    null,
  );
  const key = `${month}:${basis}:${refresh}`;
  useEffect(() => {
    if (!api) return;
    const controller = new AbortController();
    // Abort obsolete requests so a slow response cannot replace a newer month.
    // https://react.dev/reference/react/useEffect#fetching-data-with-effects
    readSummary(api, month, basis, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setLoaded({ key, ...result });
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setError({
            key,
            message:
              cause instanceof Error
                ? cause.message
                : "Could not load summary. Please reload.",
          });
      });
    return () => controller.abort();
  }, [api, month, basis, key]);
  const [start, end] = monthRange(month + "-01");
  const failure = error?.key === key ? error.message : "";
  const loading = !!api && loaded?.key !== key && !failure;
  const rows = api
    ? loaded?.key === key
      ? loaded.rows
      : []
    : filterEntries(demoRows, basis, start, end, "reviewed");
  const undated = api
    ? loaded?.key === key
      ? loaded.undated
      : 0
    : demoRows.filter((row) => {
        const field =
          basis === "statement" ? "statement_date" : "transaction_date";
        return (
          row.is_selected &&
          (row[`effective_${field}`] === undefined
            ? row[field]
            : row[`effective_${field}`]) === null
        );
      }).length;
  const summary = summarizeSpend(rows, labels);
  const monthLabel = new Intl.DateTimeFormat("en-IN", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(start + "T00:00:00Z"));
  function stepMonth(direction: number) {
    const date = new Date(start + "T00:00:00Z");
    date.setUTCMonth(date.getUTCMonth() + direction);
    const next = date.toISOString().slice(0, 7);
    if (/^(?!0000)\d{4}-\d{2}$/.test(next)) onMonth(next);
  }
  return (
    <section className="page summary-page" aria-label="Summary dashboard">
      <div className="page-heading">
        <div>
          <span className="eyebrow">YOUR MONTH AT A GLANCE</span>
          <h1>Summary</h1>
          <p>See where your money went, across all your cards.</p>
        </div>
        <button type="button" onClick={onReconciliation}>
          View reconciliation
        </button>
      </div>
      {!api && (
        <p className="demo-notice">
          Synthetic demo · All names and amounts are invented.
        </p>
      )}
      <div className="summary-controls">
        <div role="group" aria-label="Summary month navigation">
          <button
            type="button"
            aria-label="Previous summary month"
            onClick={() => stepMonth(-1)}
          >
            ←
          </button>
          <label>
            Month
            <input
              aria-label="Summary month"
              type="month"
              min="0001-01"
              max="9999-12"
              value={month}
              onChange={(event) => {
                const value = event.target.value;
                if (/^(?!0000)\d{4}-(0[1-9]|1[0-2])$/.test(value))
                  onMonth(value);
              }}
            />
          </label>
          <button
            type="button"
            aria-label="Next summary month"
            onClick={() => stepMonth(1)}
          >
            →
          </button>
        </div>
        <label>
          Date basis
          <select
            value={basis}
            onChange={(event) => setBasis(event.target.value as SummaryBasis)}
          >
            <option value="statement">Statement month</option>
            <option value="transaction">Transaction month</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => {
            setError(null);
            setRefresh((n) => n + 1);
          }}
        >
          Reload summary
        </button>
        <button type="button" onClick={() => onEntries(basis)}>
          View entries
        </button>
      </div>
      <p className="summary-method">
        Based on reviewed {basis} dates from selected imports. Card payments are
        excluded. Net spend is charges minus credits, including refunds,
        cashback and reversals. Currencies stay separate.
      </p>
      {loading && <p role="status">Loading the complete month…</p>}
      {failure && (
        <p role="alert" className="error">
          {failure}
        </p>
      )}
      {!loading && !failure && (
        <>
          {(summary.review > 0 || summary.incomplete > 0 || undated > 0) && (
            <div className="notice" role="status">
              <strong>These totals may be incomplete.</strong>
              {summary.review > 0 && (
                <p>
                  {summary.review} non-payment{" "}
                  {summary.review === 1 ? "entry needs" : "entries need"} review
                  in this month. Included amounts are provisional.
                </p>
              )}
              {summary.incomplete > 0 && (
                <p>
                  {summary.incomplete}{" "}
                  {summary.incomplete === 1 ? "entry is" : "entries are"}{" "}
                  excluded from amounts because money or currency is unknown.
                </p>
              )}
              {undated > 0 && (
                <p>
                  {undated} selected{" "}
                  {undated === 1
                    ? "entry across all imports has"
                    : "entries across all imports have"}{" "}
                  no reviewed {basis} date and cannot be placed in a month.
                </p>
              )}
              <button type="button" onClick={() => onEntries(basis)}>
                Review entries
              </button>{" "}
              <button type="button" onClick={onImports}>
                Review imports
              </button>
            </div>
          )}
          <div className="summary-context">
            <h2>{monthLabel}</h2>
            <p>
              {summary.entries} non-payment{" "}
              {summary.entries === 1 ? "entry" : "entries"} · {summary.payments}{" "}
              card
              {summary.payments === 1 ? " payment" : " payments"} excluded
            </p>
          </div>
          {basis === "statement" ? (
            <StatementBills
              bills={
                api
                  ? (loaded?.bills ?? [])
                  : demoStatementBills(demoRows).filter(
                      (bill) =>
                        bill.statement_date !== null &&
                        bill.statement_date >= start &&
                        bill.statement_date <= end,
                    )
              }
              error={api ? (loaded?.billsError ?? "") : ""}
            />
          ) : (
            <p className="summary-method">
              Bill amounts are shown in the Statement month view.
            </p>
          )}
          <h2 className="summary-spending-heading">Spending</h2>
          {summary.currencies.map((currency) => (
            <section
              key={currency.id}
              className="summary-currency"
              aria-label={`${currency.id} spending summary`}
            >
              <h3>{currency.id}</h3>
              <div className="metrics">
                <div className="summary-net">
                  <span>
                    {basis === "statement"
                      ? "Net spending this cycle"
                      : "Net spending in month"}
                  </span>
                  <strong>
                    {money(currency.charges - currency.credits, currency.id)}
                  </strong>
                  <small>{currency.count} entries with known amounts</small>
                  <small>Excludes previous balances and card payments</small>
                </div>
                <div>
                  <span>Charges</span>
                  <strong>{money(currency.charges, currency.id)}</strong>
                  <small>Purchases, fees, interest and taxes</small>
                </div>
                <div>
                  <span>Credits</span>
                  <strong>{money(currency.credits, currency.id)}</strong>
                  <small>Refunds, cashback and other credits</small>
                </div>
              </div>
              <Breakdown
                title="By card"
                currency={currency.id}
                buckets={currency.cards}
              />
              <div className="summary-grid">
                <Breakdown
                  title="By category"
                  currency={currency.id}
                  buckets={currency.categories}
                  onBucket={
                    onSpending
                      ? (id) =>
                          onSpending(
                            id,
                            basis === "transaction" ? month : "all",
                            currency.id,
                          )
                      : undefined
                  }
                />
                <Breakdown
                  title="By budget account"
                  currency={currency.id}
                  buckets={currency.accounts}
                />
              </div>
            </section>
          ))}
          {!summary.currencies.length && (
            <div className="ledger summary-empty">
              <h3>
                {summary.entries
                  ? "No amounts available"
                  : "No spending entries this month"}
              </h3>
              <p>
                {summary.entries
                  ? "Review entries with unknown amounts, directions or currencies."
                  : "Choose another month or check your imported statements."}
              </p>
              <button type="button" onClick={onImports}>
                View imports
              </button>
            </div>
          )}
          <p className="page-foot">
            Totals cover selected imported entries only. Check Imports for
            statement coverage. Contributions are tracked separately in
            Reconciliation.
          </p>
        </>
      )}
    </section>
  );
}
