import { useEffect, useRef, useState } from "react";
import { readPage, type BrowserClient } from "./client";
import { demoEntries } from "./demo";
import { filterEntries, formatAmount, type Entry, type View } from "./domain";
import Evidence from "./Evidence";
import Labels from "./Labels";
import { useLabels } from "./useLabels";
import AssignmentEditor, { type AssignmentPatch } from "./AssignmentEditor";
import Imports from "./Imports";
import type { IdentityMapping } from "./revisions-client";

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
  const [section, setSection] = useState<
    "statements" | "account" | "category" | "imports"
  >("statements");
  const labelStore = useLabels(api);
  const [demoRows, setDemoRows] = useState(() =>
    demoEntries.map((row) => ({ ...row })),
  );
  const [editing, setEditing] = useState<Entry | null>(null);
  const [notice, setNotice] = useState("");
  const editTrigger = useRef<HTMLButtonElement | null>(null);
  const ledgerHeading = useRef<HTMLHeadingElement | null>(null);
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
    const filtered = filterEntries(demoRows, view, start, end);
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
  }, [api, view, start, end, offset, invalid, refresh, demoRows]);
  function demoSourceDecision(
    candidate: string,
    base: string | null,
    mapping: IdentityMapping[] | null,
  ) {
    setDemoRows((current) =>
      current.map((row): Entry => {
        if (mapping === null)
          return row.import_id === candidate
            ? { ...row, source_state: "rejected", needs_review: false }
            : row;
        if (row.import_id === base)
          return {
            ...row,
            is_selected: false,
            source_state: "superseded",
            needs_review: false,
          };
        if (row.import_id !== candidate) return row;
        const previous = mapping.find(
          (pair) => pair.new_entry_id === row.id,
        )?.previous_entry_id;
        const old = current.find((item) => item.id === previous);
        return {
          ...row,
          is_selected: true,
          source_state: "selected",
          logical_entry_id: old?.logical_entry_id ?? old?.id ?? row.id,
          category_id: old?.category_id ?? null,
          account_id: old?.account_id ?? null,
          decision_version: old?.decision_version ?? 0,
          needs_review:
            !row.transaction_date ||
            !row.statement_date ||
            row.entry_issues.length > 0 ||
            row.import_issues.length > 0,
        };
      }),
    );
  }
  async function saveAssignments(patch: AssignmentPatch) {
    if (!editing) return;
    if (api) {
      const { error } = await api.rpc("save_entry_decision", {
        p_entry_id: editing.id,
        p_expected_version: editing.decision_version,
        p_patch: patch,
      });
      if (error)
        throw new Error(
          error.code === "PT409"
            ? "This entry changed. Cancel, refresh, and review the latest values before saving. Your draft has not overwritten them."
            : "Could not confirm the save. Reload before retrying.",
        );
      setRefresh((n) => n + 1);
    } else {
      setDemoRows((current) =>
        current.map((row) =>
          (row.logical_entry_id ?? row.id) ===
          (editing.logical_entry_id ?? editing.id)
            ? { ...row, ...patch, decision_version: row.decision_version + 1 }
            : row,
        ),
      );
    }
    setEditing(null);
    setNotice(
      "Assignments saved. Source facts and review issues are unchanged.",
    );
    ledgerHeading.current?.focus();
  }
  function labelName(
    kind: "account" | "category",
    id: string | null,
    fallback: string | null,
  ) {
    return (
      labelStore.labels.find((label) => label.kind === kind && label.id === id)
        ?.name ??
      fallback ??
      "Unassigned"
    );
  }
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
        {(
          [
            ["statements", "Statements"],
            ["account", "Accounts"],
            ["category", "Categories"],
            ["imports", "Imports"],
          ] as const
        ).map(([value, label]) => (
          <button
            type="button"
            key={value}
            className={"nav-item " + (section === value ? "nav-active" : "")}
            aria-current={section === value ? "page" : undefined}
            onClick={() => {
              setSection(value);
              setSelected(null);
              setEditing(null);
            }}
          >
            {label}
          </button>
        ))}
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
            <strong>
              {section === "statements"
                ? "Statements"
                : section === "account"
                  ? "Accounts"
                  : section === "imports"
                    ? "Imports"
                    : "Categories"}
            </strong>
          </span>
          <button className="quiet" onClick={onExit}>
            {api ? "Sign out" : "Exit demo"}
          </button>
        </header>
        {section === "imports" ? (
          <Imports
            api={api}
            demoRows={demoRows}
            onDemoDecision={demoSourceDecision}
            onChanged={() => {
              setRefresh((n) => n + 1);
              setSelected(null);
              setEditing(null);
            }}
          />
        ) : section !== "statements" ? (
          <Labels
            key={section}
            kind={section}
            {...labelStore}
            onSave={labelStore.save}
            onReload={labelStore.reload}
          />
        ) : (
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
                <span className="status-dot" />{" "}
                {api ? "PRIVATE WORKSPACE" : "INTERACTIVE DEMO"}
              </div>
            </div>
            {!api && (
              <div className="demo-notice">
                <strong>Synthetic demo</strong> • All names, amounts and
                documents below are invented. No financial data is loaded.
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
                  <h2 ref={ledgerHeading} tabIndex={-1}>
                    Statement entries
                  </h2>
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
                      <th>Account</th>
                      <th>Category</th>
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
                          <strong className="card-label">
                            {row.card_label}
                          </strong>
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
                        <td>
                          {labelName(
                            "account",
                            row.account_id,
                            row.account_name,
                          )}
                        </td>
                        <td>
                          {labelName(
                            "category",
                            row.category_id,
                            row.category_name,
                          )}
                        </td>
                        <td className={`amount ${row.direction ?? "unknown"}`}>
                          {formatAmount(
                            row.amount,
                            row.currency,
                            row.direction,
                          )}
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
                          <button
                            type="button"
                            aria-label="Edit entry"
                            disabled={
                              !row.is_selected ||
                              labelStore.loading ||
                              !!labelStore.error
                            }
                            onClick={(event) => {
                              editTrigger.current = event.currentTarget;
                              setEditing({ ...row });
                            }}
                          >
                            Edit
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
                  {total ? offset + 1 : 0}–
                  {Math.min(offset + rows.length, total)} of {total} entries
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
              Accounts and Categories are independent. Assignments do not
              resolve source issues.
            </p>
            {notice && (
              <p role="status" className="demo-notice">
                {notice}
              </p>
            )}
            {editing && (
              <AssignmentEditor
                key={editing.id}
                row={editing}
                labels={labelStore.labels}
                onSave={saveAssignments}
                onClose={() => {
                  setEditing(null);
                  editTrigger.current?.focus();
                }}
              />
            )}
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
        )}
      </main>
    </div>
  );
}
