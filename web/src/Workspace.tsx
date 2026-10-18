import { useEffect, useRef, useState } from "react";
import { readPage, type BrowserClient } from "./client";
import { demoEntries } from "./demo";
import { filterEntries, formatAmount, type Entry, type View } from "./domain";
import Evidence from "./Evidence";

export default function Workspace({
  api,
  owner,
  initialRange,
  onExit,
}: {
  api: BrowserClient | null;
  owner: string;
  initialRange: readonly [string, string];
  onExit: () => void;
}) {
  const [view, setView] = useState<View>("statement");
  const [start, setStart] = useState(initialRange[0]),
    [end, setEnd] = useState(initialRange[1]);
  const [rows, setRows] = useState<Entry[]>([]),
    [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0),
    [loading, setLoading] = useState(true);
  const [error, setError] = useState(""),
    [selected, setSelected] = useState<Entry | null>(null);
  const [refresh, setRefresh] = useState(0);
  const evidenceTrigger = useRef<HTMLButtonElement | null>(null);
  const invalid = !start || !end || start > end;
  useEffect(() => {
    const controller = new AbortController();
    setRows([]);
    setTotal(0);
    setError("");
    setLoading(true);
    if (view !== "review" && invalid) {
      setLoading(false);
      return;
    }
    const filtered = filterEntries(demoEntries, view, start, end);
    const promise = api
      ? readPage(api, view, start, end, offset, controller.signal)
      : Promise.resolve({
          rows: filtered.slice(offset, offset + 50),
          total: filtered.length,
        });
    promise
      .then((page) => {
        if (!controller.signal.aborted) {
          setRows(page.rows);
          setTotal(page.total);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            "Could not load entries. Check your connection or API setup, then retry.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, view, start, end, offset, invalid, refresh]);
  function changeView(next: View) {
    setView(next);
    setOffset(0);
    setSelected(null);
  }
  function changeRange(value: string, first: boolean) {
    if (first) setStart(value);
    else setEnd(value);
    setOffset(0);
    setSelected(null);
  }
  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Application">
        <a className="brand" href="#workspace">
          <span className="brand-mark">h.</span> hisaab
          <span className="brand-dot">●</span>
        </a>
        <p className="nav-caption">WORKSPACE</p>
        <div className="nav-active">
          <span>▤</span> Statements <span className="nav-dot">●</span>
        </div>
        <div className="sidebar-note">
          <span className="status-dot" /> Evidence preserved
          <p>
            Original facts stay original. Your decisions belong alongside them.
          </p>
        </div>
        <div className="profile">
          <span className="avatar">{owner.slice(0, 1).toUpperCase()}</span>
          <div>
            <strong>{owner}</strong>
            <small>{api ? "Private workspace" : "Synthetic demo"}</small>
          </div>
        </div>
      </nav>
      <main id="workspace">
        <header className="topbar">
          <span>
            Workspace <span className="crumb">/</span>{" "}
            <strong>Statements</strong>
          </span>
          <button className="quiet" onClick={onExit}>
            {api ? "Sign out" : "Exit demo"}
          </button>
        </header>
        <section className="page">
          <div className="page-heading">
            <div>
              <span className="eyebrow">YOUR MONTH, IN FOCUS</span>
              <h1>
                All your cards.
                <br />
                <span>One clear picture.</span>
              </h1>
              <p>
                Explore every entry, keep its evidence, and see what needs a
                closer look.
              </p>
            </div>
            <div className="read-only">
              <span className="status-dot" /> READ-ONLY PREVIEW
            </div>
          </div>
          {!api && (
            <div className="demo-notice">
              <strong>Synthetic demo</strong> • All names, amounts and documents
              below are invented. No financial data is loaded.
            </div>
          )}
          <div className="metrics">
            <div>
              <span>Matching entries</span>
              <strong>{loading ? "…" : total}</strong>
              <small>
                {view === "review"
                  ? "Across all dates"
                  : "In the selected range"}
              </small>
            </div>
            <div>
              <span>Cards on this page</span>
              <strong>{new Set(rows.map((r) => r.card_label)).size}</strong>
              <small>Combined, with provenance</small>
            </div>
            <div>
              <span>Flagged on this page</span>
              <strong>{rows.filter((r) => r.needs_review).length}</strong>
              <small>Issues, unknown dates or candidates</small>
            </div>
          </div>
          <section className="ledger" aria-label="Statement entries">
            <div className="ledger-heading">
              <div>
                <h2>Statement entries</h2>
                <p>Every row kept. Nothing silently combined.</p>
              </div>
              <button
                onClick={() => setRefresh((n) => n + 1)}
                disabled={loading}
              >
                ↻ Refresh
              </button>
            </div>
            <div className="toolbar">
              <div role="tablist" aria-label="Date view">
                {(
                  [
                    ["statement", "Statement date"],
                    ["transaction", "Transaction date"],
                    ["review", "Needs review"],
                  ] as const
                ).map(([mode, label]) => (
                  <button
                    role="tab"
                    aria-selected={view === mode}
                    key={mode}
                    className={view === mode ? "active" : ""}
                    onClick={() => changeView(mode)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="date-range">
                <label>
                  From
                  <input
                    type="date"
                    value={start}
                    disabled={view === "review"}
                    onChange={(e) => changeRange(e.target.value, true)}
                  />
                </label>
                <span>→</span>
                <label>
                  To
                  <input
                    type="date"
                    value={end}
                    disabled={view === "review"}
                    onChange={(e) => changeRange(e.target.value, false)}
                  />
                </label>
              </div>
            </div>
            <p className="view-help">
              {view === "statement"
                ? "Includes all entries from bills dated within this range, even transactions outside it."
                : view === "transaction"
                  ? "Includes selected-source entries whose printed transaction dates fall within this range."
                  : "All-date review queue: unresolved issues, unknown dates and unselected candidate imports. Candidates are excluded from normal views."}
            </p>
            {invalid && view !== "review" && (
              <p role="alert" className="error">
                Choose a valid start and end date.
              </p>
            )}
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Transaction</th>
                    <th>Card & statement</th>
                    <th>Date</th>
                    <th>Type</th>
                    <th className="amount">Amount</th>
                    <th>Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <strong>{row.description}</strong>
                        <small>
                          {row.needs_review
                            ? "● Needs review"
                            : "Selected source"}
                          {!row.is_selected && " · Candidate"}
                        </small>
                      </td>
                      <td>
                        <strong className="card-label">{row.card_label}</strong>
                        <small>
                          {row.statement_date ?? "Statement date unknown"}
                        </small>
                      </td>
                      <td className={!row.transaction_date ? "unknown" : ""}>
                        {row.transaction_date ?? "Date unknown"}
                      </td>
                      <td>
                        <span className={`type ${row.entry_type}`}>
                          {row.entry_type}
                        </span>
                      </td>
                      <td className={`amount ${row.direction ?? "unknown"}`}>
                        {formatAmount(row.amount, row.currency, row.direction)}
                      </td>
                      <td>
                        <button
                          className="evidence-link"
                          aria-label="View evidence"
                          aria-expanded={selected?.id === row.id}
                          aria-controls={
                            selected?.id === row.id
                              ? "source-evidence"
                              : undefined
                          }
                          onClick={(event) => {
                            evidenceTrigger.current = event.currentTarget;
                            setSelected({ ...row });
                          }}
                        >
                          View ↗
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!loading && !error && rows.length === 0 && (
                <div className="empty">
                  <h3>No matching entries</h3>
                  <p>
                    Try another date range or check Needs review for undated
                    entries and candidates.
                  </p>
                </div>
              )}
              {loading && (
                <p className="empty" role="status">
                  Loading your entries…
                </p>
              )}
            </div>
            <footer className="table-footer">
              <span>
                {total ? offset + 1 : 0}–{Math.min(offset + rows.length, total)}{" "}
                of {total} entries
              </span>
              <div>
                <button
                  disabled={loading || offset === 0}
                  onClick={() => {
                    setOffset((n) => n - 50);
                    setSelected(null);
                  }}
                >
                  Previous
                </button>
                <button
                  disabled={loading || offset + 50 >= total}
                  onClick={() => {
                    setOffset((n) => n + 50);
                    setSelected(null);
                  }}
                >
                  Next
                </button>
              </div>
            </footer>
          </section>
          <p className="page-foot">
            <span className="status-dot" /> Source facts are immutable.
            Accounts, categories and review editing are the next milestone.
          </p>
          {selected && (
            <Evidence
              key={selected.id}
              row={selected}
              api={api}
              onClose={() => {
                setSelected(null);
                evidenceTrigger.current?.focus();
              }}
            />
          )}
        </section>
      </main>
    </div>
  );
}
