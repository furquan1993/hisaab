import { useState } from "react";
import { sortEntries } from "./domain";
import { decimalText, fundingMoney } from "./funding-domain";
import { reviewedValues } from "./review-domain";
import {
  spendingBuckets,
  spendingKey,
  spendingRows,
  spendingTotals,
  ungrouped,
  type SpendingEntry,
  type SpendingGroup,
  type SpendingView,
} from "./spending-domain";
import type { SpendingStore } from "./useSpending";
import type { Label } from "./useLabels";
import SpendingAssignments from "./SpendingAssignments";
import SpendingEntryList from "./SpendingEntryList";
import SpendingGroupForm from "./SpendingGroupForm";

export type SpendingFocus = {
  view: SpendingView;
  id: string;
  period: string;
  currency?: string;
};
const money = (amount: bigint, currency: string) =>
  fundingMoney(decimalText(amount), currency === "unknown" ? null : currency);
const monthName = (month: string) =>
  new Intl.DateTimeFormat("en-IN", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(month + "-01T00:00:00Z"));

export default function Spending({
  store,
  labels,
  demo,
  initialFocus,
  onCategories,
}: {
  store: SpendingStore;
  labels: Label[];
  demo: boolean;
  initialFocus?: SpendingFocus;
  onCategories: () => void;
}) {
  const [view, setView] = useState<SpendingView>(initialFocus?.view ?? "trip");
  const [selection, setSelection] = useState(initialFocus?.id ?? "");
  const [period, setPeriod] = useState(initialFocus?.period ?? "all");
  const [chosenCurrency, setChosenCurrency] = useState(
    initialFocus?.currency ?? "",
  );
  const [filter, setFilter] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [form, setForm] = useState<SpendingGroup | null | undefined>(undefined);
  const [assigning, setAssigning] = useState(false);
  const [notice, setNotice] = useState("");
  const all = spendingRows(store.rows);
  const months = [
    ...new Set(
      all
        .map((r) => reviewedValues(r).transaction_date?.slice(0, 7))
        .filter((m): m is string => !!m),
    ),
  ]
    .sort()
    .reverse();
  const currencies = [
    ...new Set(all.map((r) => reviewedValues(r).currency ?? "unknown")),
  ].sort();
  const currency = currencies.includes(chosenCurrency)
    ? chosenCurrency
    : (currencies.find((c) => c !== "unknown") ?? currencies[0] ?? "INR");
  const rows = spendingRows(all, period).filter(
    (r) => (reviewedValues(r).currency ?? "unknown") === currency,
  );
  const buckets = spendingBuckets(rows, view, labels);
  const choices =
    view === "trip"
      ? [
          ...store.groups.map((g) => ({
            id: g.id,
            name: g.name,
            archived: g.is_archived,
          })),
          { id: ungrouped, name: "Ungrouped", archived: false },
        ]
      : buckets.map((b) => ({ id: b.id, name: b.name, archived: false }));
  const selected = choices.find((c) => c.id === selection) ?? choices[0];
  const group =
    view === "trip"
      ? store.groups.find((g) => g.id === selected?.id)
      : undefined;
  const selectedRows = rows.filter(
    (r) => spendingKey(r, view) === selected?.id,
  );
  const totals = spendingTotals(selectedRows);
  const breakdownView = view === "trip" ? "category" : "trip";
  const breakdown = spendingBuckets(selectedRows, breakdownView, labels);
  const maximum = breakdown.reduce((max, b) => {
    const absolute = b.net < 0n ? -b.net : b.net;
    return absolute > max ? absolute : max;
  }, 1n);
  const shown = sortEntries(
    selectedRows.filter(
      (r) => !filter || spendingKey(r, breakdownView) === filter,
    ),
    "newest",
  ) as SpendingEntry[];
  const pageOffset = Math.min(
    offset,
    Math.max(0, Math.floor((shown.length - 1) / 50) * 50),
  );
  const reset = () => {
    setFilter(null);
    setOffset(0);
    setAssigning(false);
    setForm(undefined);
    setNotice("");
  };
  const changeView = (next: SpendingView) => {
    setView(next);
    setSelection("");
    reset();
  };
  const cards = new Set(selectedRows.map((r) => r.card_id ?? r.card_label))
    .size;
  const undated = all.filter((r) => !reviewedValues(r).transaction_date).length;
  return (
    <section className="page spending-page">
      <span className="eyebrow">YOUR SPENDING, YOUR WAY</span>
      <h1>Where it all went.</h1>
      <p className="spending-intro">
        Everyday categories. Memorable trips. All your cards together.
      </p>
      <div className="spending-toolbar">
        <div className="spending-tabs" role="group" aria-label="Group spending">
          <button
            type="button"
            aria-pressed={view === "category"}
            disabled={store.busy}
            onClick={() => changeView("category")}
          >
            By category
          </button>
          <button
            type="button"
            aria-pressed={view === "trip"}
            disabled={store.busy}
            onClick={() => changeView("trip")}
          >
            Trips &amp; groups
          </button>
        </div>
        <div className="spending-period-controls">
          <label>
            Period
            <select
              aria-label="Spending period"
              value={period}
              disabled={store.busy}
              onChange={(e) => {
                setPeriod(e.target.value);
                reset();
              }}
            >
              <option value="all">All dates</option>
              {!months.includes(period) && period !== "all" && (
                <option value={period}>{monthName(period)}</option>
              )}
              {months.map((m) => (
                <option key={m} value={m}>
                  {monthName(m)}
                </option>
              ))}
            </select>
          </label>
          {currencies.length > 1 && (
            <label>
              Currency
              <select
                aria-label="Spending currency"
                value={currency}
                disabled={store.busy}
                onChange={(e) => {
                  setChosenCurrency(e.target.value);
                  reset();
                }}
              >
                {currencies.map((c) => (
                  <option key={c} value={c}>
                    {c === "unknown" ? "Currency unknown" : c}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button
            type="button"
            disabled={store.busy || store.loading}
            onClick={() => {
              reset();
              store.reload();
            }}
          >
            Reload spending
          </button>
        </div>
      </div>
      {demo && (
        <p className="demo-notice">
          Synthetic demo. Groups and assignments stay in memory and reset on
          reload or exit.
        </p>
      )}
      {store.loading && <p role="status">Loading spending…</p>}
      {store.error && (
        <p role="alert" className="error">
          {store.error}
        </p>
      )}
      {notice && (
        <p role="status" className="demo-notice">
          {notice}
        </p>
      )}
      {!store.loading && !store.error && (
        <>
          <div className="spending-content">
            <aside
              className="spending-groups"
              aria-label={
                view === "trip" ? "Trips and groups" : "Spending categories"
              }
            >
              <div className="spending-group-heading">
                <span>{view === "trip" ? "TRIPS & GROUPS" : "CATEGORIES"}</span>
                <button
                  type="button"
                  disabled={store.busy}
                  onClick={() => {
                    setAssigning(false);
                    if (view === "trip") setForm(null);
                    else onCategories();
                  }}
                >
                  {view === "trip" ? "+ New group" : "Manage"}
                </button>
              </div>
              {choices.map((choice) => {
                const bucket = buckets.find((b) => b.id === choice.id);
                return (
                  <button
                    key={choice.id}
                    type="button"
                    className="spending-group"
                    aria-pressed={selected?.id === choice.id}
                    disabled={store.busy}
                    onClick={() => {
                      setSelection(choice.id);
                      reset();
                    }}
                  >
                    <strong>
                      {choice.name}
                      {choice.archived ? " (archived)" : ""}
                    </strong>
                    <small>
                      {money(bucket?.net ?? 0n, currency)} ·{" "}
                      {bucket?.count ?? 0}{" "}
                      {(bucket?.count ?? 0) === 1 ? "entry" : "entries"}
                    </small>
                  </button>
                );
              })}
              {!choices.length && (
                <p className="muted">No category spending in this period.</p>
              )}
            </aside>
            <div className="spending-detail-column">
              {form !== undefined && (
                <SpendingGroupForm
                  key={form?.id ?? "new"}
                  group={form}
                  store={store}
                  onClose={() => setForm(undefined)}
                  onSaved={(saved) => {
                    setForm(undefined);
                    setView("trip");
                    setSelection(saved.id);
                    setFilter(null);
                    setOffset(0);
                    setNotice("Group saved.");
                  }}
                />
              )}
              <section
                className="spending-detail"
                aria-label="Selected spending"
              >
                <div className="spending-overview">
                  <div className="spending-detail-heading">
                    <div>
                      <h2>
                        {selected?.name ?? "Your spending"}
                        {group?.is_archived ? " (archived)" : ""}
                      </h2>
                      <p>
                        {totals.count}{" "}
                        {totals.count === 1 ? "entry" : "entries"} across{" "}
                        {cards} {cards === 1 ? "card" : "cards"}
                      </p>
                    </div>
                    <div className="spending-detail-actions">
                      {view === "trip" && (
                        <button
                          type="button"
                          disabled={
                            store.busy || group?.is_archived || !all.length
                          }
                          onClick={() => {
                            setAssigning(!assigning);
                            setForm(undefined);
                          }}
                        >
                          {group ? "Add / move entries" : "Assign entries"}
                        </button>
                      )}
                      {group && (
                        <button
                          type="button"
                          disabled={store.busy}
                          onClick={() => {
                            setForm(group);
                            setAssigning(false);
                          }}
                        >
                          Manage group
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="spending-metrics">
                    <div>
                      <span>Net spend</span>
                      <strong className="spending-net">
                        {money(totals.net, currency)}
                      </strong>
                    </div>
                    <div>
                      <span>Charges</span>
                      <strong>{money(totals.charges, currency)}</strong>
                    </div>
                    <div>
                      <span>Credits &amp; refunds</span>
                      <strong>{money(totals.credits, currency)}</strong>
                    </div>
                  </div>
                  {(totals.incomplete > 0 || totals.review > 0) && (
                    <p className="spending-data-note">
                      {totals.incomplete > 0 &&
                        `${totals.incomplete} entries have incomplete amounts, currency or direction and are excluded from totals. `}
                      {totals.review > 0 &&
                        `${totals.review} ${totals.review === 1 ? "entry needs" : "entries need"} review; totals are provisional.`}
                    </p>
                  )}
                  <div className="spending-breakdown-heading">
                    <h3>
                      {view === "trip" ? "By category" : "By trip or group"}
                    </h3>
                    {filter && (
                      <button
                        type="button"
                        onClick={() => {
                          setFilter(null);
                          setOffset(0);
                        }}
                      >
                        Clear filter
                      </button>
                    )}
                  </div>
                  <div className="spending-breakdown">
                    {breakdown.map((bucket) => (
                      <button
                        type="button"
                        key={bucket.id}
                        className="spending-bar-row"
                        aria-pressed={filter === bucket.id}
                        onClick={() => {
                          setFilter(filter === bucket.id ? null : bucket.id);
                          setOffset(0);
                        }}
                      >
                        <span>{bucket.name}</span>
                        <span className="spending-bar-track">
                          <span
                            style={{
                              width: `${Number(((bucket.net < 0n ? -bucket.net : bucket.net) * 10000n) / maximum) / 100}%`,
                            }}
                          />
                        </span>
                        <span className="spending-money">
                          {money(bucket.net, currency)}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
                {assigning && (
                  <SpendingAssignments
                    key={selected?.id}
                    store={store}
                    labels={labels}
                    initialGroup={group?.id ?? null}
                    onClose={() => setAssigning(false)}
                    onSaved={() => {
                      setAssigning(false);
                      setNotice(
                        "Trip assignments saved. Category and account assignments are unchanged.",
                      );
                    }}
                  />
                )}
                <div className="spending-entries-heading">
                  <h3>
                    {filter
                      ? breakdown.find((b) => b.id === filter)?.name
                      : "All transactions"}
                  </h3>
                  <span>
                    {shown.length} entries ·{" "}
                    {currency === "unknown" ? "Currency unknown" : currency}
                  </span>
                </div>
                <SpendingEntryList
                  rows={shown.slice(pageOffset, pageOffset + 50)}
                  labels={labels}
                />
                {!shown.length && (
                  <p className="empty">
                    {group
                      ? "No entries in this group for the selected period and currency. Add entries to get started."
                      : "No spending in this selection."}
                  </p>
                )}
                {shown.length > 50 && (
                  <div className="spending-pagination form-actions">
                    <span>
                      {pageOffset + 1}–{Math.min(pageOffset + 50, shown.length)}{" "}
                      of {shown.length}
                    </span>
                    <button
                      type="button"
                      disabled={!pageOffset}
                      onClick={() => setOffset(pageOffset - 50)}
                    >
                      Previous transactions
                    </button>
                    <button
                      type="button"
                      disabled={pageOffset + 50 >= shown.length}
                      onClick={() => setOffset(pageOffset + 50)}
                    >
                      Next transactions
                    </button>
                  </div>
                )}
              </section>
            </div>
          </div>
          {period !== "all" && undated > 0 && (
            <p className="spending-foot">
              {undated} entries with unknown transaction dates appear under All
              dates.
            </p>
          )}
        </>
      )}
      <p className="spending-foot">
        Spending uses reviewed transaction dates. Card repayments are excluded.
        Reconcile contributions by account in Reconciliation.
      </p>
    </section>
  );
}
