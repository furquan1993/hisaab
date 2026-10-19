import { compareLabelNames } from "./label-order";
import { Fragment, useEffect, useRef, useState } from "react";
import { readPage, type BrowserClient } from "./client";
import { demoEntries } from "./demo";
import {
  filterEntries,
  sortEntries,
  type DateSort,
  formatAmount,
  monthRange,
  type Entry,
  type View,
} from "./domain";
import Reconciliation from "./Reconciliation";
import Summary from "./Summary";
import Spending, { type SpendingFocus } from "./Spending";
import { useSpending } from "./useSpending";
import EntryTripEditor from "./EntryTripEditor";
import { assignEntries } from "./auto-assignments";
import type { Confirmation, Contribution } from "./funding-domain";
import Evidence from "./Evidence";
import FriendlyDescriptionEditor from "./FriendlyDescriptionEditor";
import Labels from "./Labels";
import { useLabels } from "./useLabels";
import AssignmentEditor, { type AssignmentPatch } from "./AssignmentEditor";
import Imports from "./Imports";
import ReviewEditor, { type ReviewSave } from "./ReviewEditor";
import {
  applyDemoReview,
  reviewedValues,
  requiresReview,
  issueKey,
} from "./review-domain";
import type { StatementReviewSave } from "./StatementReview";
import type { IdentityMapping } from "./revisions-client";

export default function Workspace({
  api,
  owner,
  ownerId,
  initialRange,
  onExit,
}: {
  api: BrowserClient | null;
  owner: string;
  ownerId?: string;
  initialRange: readonly [string, string];
  onExit: () => void;
}) {
  const [section, setSection] = useState<
    | "summary"
    | "statements"
    | "account"
    | "category"
    | "imports"
    | "reconciliation"
    | "spending"
  >("statements");
  const labelStore = useLabels(api, ownerId);
  const [fundingMonth, setFundingMonth] = useState(initialRange[0].slice(0, 7));
  const [fundingBusy, setFundingBusy] = useState(false);
  const [contributions, setContributions] = useState<Contribution[]>([]);
  const [confirmations, setConfirmations] = useState<Confirmation[]>([]);
  const demoRows = useRef(demoEntries.map((row) => ({ ...row })));
  function setDemoRows(update: (current: Entry[]) => Entry[]) {
    setLoading(true);
    demoRows.current = update(demoRows.current);
    setRefresh((n) => n + 1);
  }
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [assignmentError, setAssignmentError] = useState("");
  const pendingFocus = useRef<string | null>(null);
  const [editing, setEditing] = useState<Entry | null>(null);
  const [describing, setDescribing] = useState<Entry | null>(null);
  const descriptionTrigger = useRef<HTMLButtonElement | null>(null);
  const [search, setSearch] = useState("");
  const [reviewing, setReviewing] = useState<Entry | null>(null);
  const reviewTrigger = useRef<HTMLButtonElement | null>(null);
  const [notice, setNotice] = useState("");
  const [autoAssignmentNotice, setAutoAssignmentNotice] = useState("");
  const editTrigger = useRef<HTMLButtonElement | null>(null);
  const ledgerHeading = useRef<HTMLHeadingElement | null>(null);
  const [view, setView] = useState<View>("statement");
  const [dateSort, setDateSort] = useState<DateSort>("newest");
  const [dateBasis, setDateBasis] = useState<"original" | "reviewed">(
    "original",
  );
  const [start, setStart] = useState(initialRange[0]),
    [end, setEnd] = useState(initialRange[1]);
  const [rows, setRows] = useState<Entry[]>([]),
    [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0),
    [loading, setLoading] = useState(true);
  const [error, setError] = useState(""),
    [selected, setSelected] = useState<Entry | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [spendingFocus, setSpendingFocus] = useState<SpendingFocus>();
  const [tripEntry, setTripEntry] = useState<Entry | null>(null);
  const tripTrigger = useRef<HTMLButtonElement | null>(null);
  const spendingStore = useSpending(
    api,
    ownerId,
    demoRows.current,
    section === "spending" || !!tripEntry,
    refresh,
  );
  const evidenceTrigger = useRef<HTMLButtonElement | null>(null);
  const invalid = !start || !end || start > end;
  useEffect(() => {
    const controller = new AbortController();
    setRows([]);
    setTotal(0);
    setAutoAssignmentNotice("");
    setError("");
    setLoading(true);
    if (view !== "review" && invalid) {
      setLoading(false);
      return;
    }
    const filtered = sortEntries(
      filterEntries(demoRows.current, view, start, end, dateBasis).filter(
        (row) =>
          [
            row.description,
            row.effective_description,
            row.friendly_description,
          ].some((value) =>
            value?.toLowerCase().includes(search.toLowerCase().trim()),
          ),
      ),
      dateSort,
    );
    const promise = api
      ? readPage(
          api,
          view,
          start,
          end,
          offset,
          controller.signal,
          dateBasis,
          dateSort,
          search,
        )
      : Promise.resolve({
          rows: filtered.slice(offset, offset + 50),
          total: filtered.length,
        });
    promise
      .then(async (loaded) => {
        let page = loaded;
        if (api && ownerId && !controller.signal.aborted) {
          try {
            const assigned = await assignEntries(
              api,
              ownerId,
              loaded.rows,
              controller.signal,
            );
            if (assigned > 0 && !controller.signal.aborted) {
              page = await readPage(
                api,
                view,
                start,
                end,
                offset,
                controller.signal,
                dateBasis,
                dateSort,
                search,
              );
              labelStore.reload();
            }
          } catch (error) {
            if (!controller.signal.aborted)
              setAutoAssignmentNotice(
                error instanceof Error
                  ? error.message
                  : "Automatic assignments could not be confirmed. Reload to retry.",
              );
          }
        }
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
  }, [
    api,
    ownerId,
    view,
    start,
    end,
    offset,
    invalid,
    refresh,
    dateBasis,
    dateSort,
    search,
  ]);
  useEffect(() => {
    if (loading || saving || !pendingFocus.current) return;
    const toggle = document.getElementById(pendingFocus.current);
    (toggle ?? ledgerHeading.current)?.focus({ preventScroll: true });
    pendingFocus.current = null;
  }, [loading, rows, saving]);
  function resetDetails() {
    setTripEntry(null);
    setDescribing(null);
    setExpandedId(null);
    setSelected(null);
    setEditing(null);
    setReviewing(null);
    setNotice("");
  }
  // Native disclosure buttons preserve table semantics and support Enter/Space.
  // https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/
  function toggleRow(id: string) {
    if (saving) return;
    resetDetails();
    setExpandedId(expandedId === id ? null : id);
  }
  async function saveEntry(action: () => Promise<void>) {
    setSaving(true);
    try {
      await action();
    } finally {
      setSaving(false);
    }
  }
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
          friendly_description: old?.friendly_description ?? null,
          friendly_description_version: old?.friendly_description_version ?? 0,
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
  function demoStatementReview(source: string, save: StatementReviewSave) {
    setDemoRows((current) =>
      current.map((row): Entry => {
        if (row.import_id !== source) return row;
        const date = save.date ?? row.statement_date;
        const unresolved = row.import_issues.filter(
          (issue) =>
            !save.acknowledged.includes(issueKey(issue)) &&
            !(
              [
                "statement_date_missing_or_invalid",
                "statement_date_conflict",
              ].includes(issue.code) && date
            ),
        );
        const next = {
          ...row,
          effective_statement_date: date,
          statement_date_override: save.date,
          import_review_version: row.import_review_version + 1,
          import_acknowledged: save.acknowledged,
          unresolved_import_issues: unresolved,
          import_review_stale: false,
        };
        return { ...next, needs_review: requiresReview(next) };
      }),
    );
  }
  async function saveDescription(description: string | null) {
    if (!describing) return;
    let saved = {
      friendly_description: description,
      friendly_description_version: describing.friendly_description_version + 1,
    };
    if (api) {
      const { data, error } = await api.rpc("save_friendly_description", {
        p_entry_id: describing.id,
        p_expected_version: describing.friendly_description_version,
        p_description: description,
      });
      if (error)
        throw Error(
          error.code === "PT409"
            ? "The description or source changed. Your draft is kept; close and refresh before saving."
            : "Could not confirm the save. Reload before retrying.",
        );
      saved = data;
    }
    const update = (current: Entry[]) =>
      current.map((row) =>
        (row.logical_entry_id ?? row.id) ===
        (describing.logical_entry_id ?? describing.id)
          ? { ...row, ...saved }
          : row,
      );
    if (!api) demoRows.current = update(demoRows.current);
    setRows(update);
    pendingFocus.current = "entry-toggle-" + describing.id;
    setDescribing(null);
    setNotice("Description saved.");
    if (search.trim()) {
      setLoading(true);
      setRefresh((n) => n + 1);
    }
  }
  async function saveReview(save: ReviewSave) {
    if (!reviewing) return;
    if (api) {
      const { error } = await api.rpc("review_entry", {
        p_entry_id: reviewing.id,
        p_expected_version: reviewing.decision_version,
        p_overrides: save.patch,
        p_acknowledged: save.acknowledged,
        p_reason: save.reason,
        p_confirm_source: save.confirmSource,
      });
      if (error)
        throw Error(
          error.code === "PT409"
            ? "The entry or source changed. Your draft is kept; close and refresh before reviewing the latest values."
            : "Could not confirm the review. Check the values and reload before retrying.",
        );
      setLoading(true);
      setRefresh((n) => n + 1);
    } else
      setDemoRows((current) =>
        current.map((row) =>
          row.id === reviewing.id
            ? applyDemoReview(row, save.patch, save.acknowledged)
            : row,
        ),
      );
    pendingFocus.current = "entry-toggle-" + reviewing.id;
    setReviewing(null);
    setNotice("Review saved. Original facts and flags are preserved.");
  }
  async function saveAssignments(
    patch: Partial<AssignmentPatch>,
    entry = editing,
    focusId?: string,
  ) {
    if (!entry) return;
    let assignments = patch;
    let version = entry.decision_version + 1;
    if (api) {
      const { data, error } = await api.rpc("save_entry_decision", {
        p_entry_id: entry.id,
        p_expected_version: entry.decision_version,
        p_patch: patch,
      });
      if (error)
        throw new Error(
          error.code === "PT409"
            ? "This entry changed. Refresh and review the latest values before saving. Your changes have not overwritten them."
            : "Could not confirm the save. Reload before retrying.",
        );
      assignments = {
        account_id: data.account_id,
        category_id: data.category_id,
      };
      version = data.version;
    }
    const update = (current: Entry[]) =>
      current.map((row) => {
        if (
          (row.logical_entry_id ?? row.id) !==
          (entry.logical_entry_id ?? entry.id)
        )
          return row;
        const next = { ...row, ...assignments, decision_version: version };
        for (const kind of ["account", "category"] as const) {
          const field = kind === "account" ? "account_id" : "category_id";
          if (field in assignments)
            next[`${kind}_name`] =
              labelStore.labels.find(
                (label) => label.kind === kind && label.id === next[field],
              )?.name ?? null;
        }
        return next;
      });
    if (!api) demoRows.current = update(demoRows.current);
    setRows(update);
    pendingFocus.current = focusId ?? "entry-toggle-" + entry.id;
    setEditing(null);
    setNotice(
      "Assignments saved. Source facts and review issues are unchanged.",
    );
  }
  function assignmentSelect(row: Entry, kind: "account" | "category") {
    const field = kind === "account" ? "account_id" : "category_id";
    const current = row[field] ?? "";
    const id = `entry-${kind}-${row.id}`;
    return (
      <select
        id={id}
        className="inline-assignment"
        aria-label={`${kind === "account" ? "Account" : "Category"} for ${reviewedValues(row).description}`}
        value={current}
        disabled={
          saving ||
          !!editing ||
          !!reviewing ||
          !row.is_selected ||
          labelStore.loading ||
          !!labelStore.error
        }
        onChange={(event) => {
          const value = event.target.value || null;
          setAssignmentError("");
          void saveEntry(() =>
            saveAssignments({ [field]: value }, row, id),
          ).catch((error: unknown) =>
            setAssignmentError(
              error instanceof Error
                ? error.message
                : "Could not save the assignment. Reload before retrying.",
            ),
          );
        }}
      >
        <option value="">Unassigned</option>
        {labelStore.labels
          .filter(
            (label) =>
              label.kind === kind &&
              (!label.is_archived || label.id === current),
          )
          .sort((a, b) => compareLabelNames(a.name, b.name))
          .map((label) => (
            <option key={label.id} value={label.id}>
              {label.name}
              {label.is_archived ? " (archived)" : ""}
            </option>
          ))}
      </select>
    );
  }
  function changeView(next: View) {
    setView(next);
    setOffset(0);
    resetDetails();
  }
  const monthDate = start ? new Date(start + "T00:00:00Z") : null;
  const monthLabel =
    monthDate && !Number.isNaN(monthDate.getTime())
      ? new Intl.DateTimeFormat("en", {
          month: "long",
          year: "numeric",
          timeZone: "UTC",
        }).format(monthDate)
      : "Choose a date";
  function changeMonth(direction: -1 | 1) {
    if (!monthDate || Number.isNaN(monthDate.getTime())) return;
    const target = new Date(monthDate);
    target.setUTCDate(1);
    target.setUTCMonth(target.getUTCMonth() + direction);
    const [first, last] = monthRange(target.toISOString().slice(0, 10));
    setStart(first);
    setEnd(last);
    setOffset(0);
    resetDetails();
  }
  function changeRange(value: string, first: boolean) {
    if (first) setStart(value);
    else setEnd(value);
    setOffset(0);
    resetDetails();
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
            ["summary", "Summary"],
            ["spending", "Spending"],
            ["statements", "Statements"],
            ["reconciliation", "Reconciliation"],
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
            disabled={fundingBusy || spendingStore.busy}
            onClick={() => {
              setSection(value);
              if (value === "spending") setSpendingFocus(undefined);
              resetDetails();
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
              {section === "summary"
                ? "Summary"
                : section === "spending"
                  ? "Spending"
                  : section === "statements"
                    ? "Statements"
                    : section === "reconciliation"
                      ? "Reconciliation"
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
        {api && section === "statements" && (
          <p className="demo-notice">
            Accounts and categories are assigned when a clear match is
            available. Your changes teach future matches.
          </p>
        )}
        {autoAssignmentNotice && (
          <p role="status" className="demo-notice">
            {autoAssignmentNotice}
          </p>
        )}
        {section === "summary" ? (
          <Summary
            api={api}
            month={fundingMonth}
            onMonth={setFundingMonth}
            demoRows={demoRows.current}
            labels={labelStore.labels}
            onEntries={(basis) => {
              const [first, last] = monthRange(fundingMonth + "-01");
              setStart(first);
              setEnd(last);
              setDateBasis("reviewed");
              changeView(basis);
              setSection("statements");
            }}
            onImports={() => setSection("imports")}
            onReconciliation={() => setSection("reconciliation")}
            onSpending={(id, period, currency) => {
              setSpendingFocus({
                view: "category",
                id: id === "unassigned" ? "uncategorized" : id,
                period,
                currency,
              });
              setSection("spending");
              resetDetails();
            }}
          />
        ) : section === "spending" ? (
          <Spending
            store={spendingStore}
            labels={labelStore.labels}
            demo={!api}
            initialFocus={spendingFocus}
            onCategories={() => setSection("category")}
          />
        ) : section === "imports" ? (
          <Imports
            api={api}
            demoRows={demoRows.current}
            onDemoDecision={demoSourceDecision}
            onDemoCoverage={demoStatementReview}
            onChanged={() => {
              setRefresh((n) => n + 1);
              setSelected(null);
              setEditing(null);
            }}
          />
        ) : section === "reconciliation" ? (
          <Reconciliation
            api={api}
            ownerId={ownerId}
            month={fundingMonth}
            onMonth={setFundingMonth}
            demoRows={demoRows.current}
            labels={labelStore.labels}
            receipts={contributions}
            confirmations={confirmations}
            onReceipt={(receipt) =>
              setContributions((current) => [...current, receipt])
            }
            onConfirm={(confirmation) =>
              setConfirmations((current) => [...current, confirmation])
            }
            onEntries={() => {
              const [first, last] = monthRange(fundingMonth + "-01");
              setStart(first);
              setEnd(last);
              setDateBasis("reviewed");
              changeView("statement");
              setSection("statements");
            }}
            onImports={() => setSection("imports")}
            onBusyChange={setFundingBusy}
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
                  onClick={() => {
                    resetDetails();
                    setRefresh((n) => n + 1);
                  }}
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
                {view !== "review" && (
                  <div
                    className="month-navigation"
                    role="group"
                    aria-label="Browse months"
                  >
                    <button
                      type="button"
                      aria-label="Previous month"
                      disabled={!start || saving}
                      onClick={() => changeMonth(-1)}
                    >
                      ←
                    </button>
                    <span aria-live="polite">{monthLabel}</span>
                    <button
                      type="button"
                      aria-label="Next month"
                      disabled={!start || saving}
                      onClick={() => changeMonth(1)}
                    >
                      →
                    </button>
                  </div>
                )}
                <div className="date-range description-search">
                  <label>
                    Search descriptions
                    <input
                      type="search"
                      maxLength={500}
                      value={search}
                      disabled={saving}
                      onChange={(event) => {
                        setSearch(event.target.value);
                        setOffset(0);
                        resetDetails();
                      }}
                    />
                  </label>
                </div>
                <div className="date-range">
                  <label>
                    Sort by transaction date
                    <select
                      aria-label="Sort by transaction date"
                      value={dateSort}
                      disabled={saving}
                      onChange={(event) => {
                        setDateSort(event.target.value as DateSort);
                        setOffset(0);
                        resetDetails();
                      }}
                    >
                      <option value="newest">Newest first</option>
                      <option value="oldest">Oldest first</option>
                    </select>
                  </label>
                  <label>
                    Filter dates
                    <select
                      aria-label="Filter dates"
                      value={dateBasis}
                      disabled={view === "review"}
                      onChange={(event) => {
                        setDateBasis(
                          event.target.value as "original" | "reviewed",
                        );
                        setOffset(0);
                        resetDetails();
                      }}
                    >
                      <option value="original">Original extracted dates</option>
                      <option value="reviewed">Reviewed dates</option>
                    </select>
                  </label>
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
                {view === "review"
                  ? "All-date review queue: unresolved issues, unknown dates and unselected candidates. Superseded and rejected sources remain in Imports history."
                  : (view === "statement"
                      ? "Includes every entry from bills within the selected range. "
                      : "Includes selected-source entries whose transaction dates fall within this range. ") +
                    (dateBasis === "original"
                      ? "Filtering uses original extracted dates; verified corrections are shown alongside them."
                      : "Filtering uses reviewed dates, falling back to extracted values when no correction exists.")}
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
              {assignmentError && (
                <p role="alert" className="error">
                  {assignmentError}
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
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const effective = reviewedValues(row);
                      return (
                        <Fragment key={row.id}>
                          <tr
                            className={
                              "entry-row" +
                              (expandedId === row.id ? " expanded" : "")
                            }
                            onClick={(event) => {
                              if (
                                !(event.target as HTMLElement).closest(
                                  "button, select",
                                )
                              )
                                toggleRow(row.id);
                            }}
                          >
                            <td>
                              <div className="entry-summary">
                                <button
                                  type="button"
                                  id={"entry-toggle-" + row.id}
                                  className="entry-toggle"
                                  aria-label={
                                    "Details for " + effective.description
                                  }
                                  aria-expanded={expandedId === row.id}
                                  aria-controls={
                                    expandedId === row.id
                                      ? "entry-details-" + row.id
                                      : undefined
                                  }
                                  disabled={saving}
                                  onClick={() => toggleRow(row.id)}
                                >
                                  <span aria-hidden="true">
                                    {expandedId === row.id ? "▾" : "▸"}
                                  </span>
                                </button>
                                <div>
                                  <strong
                                    className="entry-description"
                                    title={effective.description ?? undefined}
                                  >
                                    {row.friendly_description ??
                                      effective.description}
                                  </strong>
                                  {row.friendly_description && (
                                    <small>Statement: {row.description}</small>
                                  )}
                                  {row.friendly_description &&
                                    effective.description !==
                                      row.description && (
                                      <small>
                                        Reviewed: {effective.description}
                                      </small>
                                    )}
                                  {!row.friendly_description &&
                                    effective.description !==
                                      row.description && (
                                      <small>
                                        Extracted: {row.description}
                                      </small>
                                    )}
                                  <small>
                                    {row.needs_review
                                      ? "● Needs review"
                                      : "Selected source"}
                                    {!row.is_selected && " · Candidate"}
                                  </small>
                                </div>
                              </div>
                            </td>
                            <td>
                              <strong className="card-label">
                                {row.card_label}
                              </strong>
                              <small>
                                {(row.effective_statement_date === undefined
                                  ? row.statement_date
                                  : row.effective_statement_date) ??
                                  "Statement date unknown"}
                                {row.effective_statement_date !== undefined &&
                                  row.effective_statement_date !==
                                    row.statement_date && (
                                    <span>
                                      {" "}
                                      · Extracted:{" "}
                                      {row.statement_date ?? "Unknown"}
                                    </span>
                                  )}
                              </small>
                            </td>
                            <td
                              className={
                                !effective.transaction_date ? "unknown" : ""
                              }
                            >
                              {effective.transaction_date ?? "Date unknown"}
                              {effective.transaction_date !==
                                row.transaction_date && (
                                <small>
                                  Extracted: {row.transaction_date ?? "Unknown"}
                                </small>
                              )}
                            </td>
                            <td>
                              <span className={`type ${effective.entry_type}`}>
                                {effective.entry_type}
                              </span>
                            </td>
                            <td>{assignmentSelect(row, "account")}</td>
                            <td>{assignmentSelect(row, "category")}</td>
                            <td
                              className={`amount ${effective.direction ?? "unknown"}`}
                            >
                              {formatAmount(
                                effective.amount,
                                effective.currency,
                                effective.direction,
                              )}
                            </td>
                          </tr>
                          {expandedId === row.id && (
                            <tr className="entry-detail-row">
                              <td colSpan={7}>
                                <div
                                  id={"entry-details-" + row.id}
                                  className="entry-details"
                                  role="region"
                                  aria-label={
                                    "Details for " + effective.description
                                  }
                                >
                                  <div
                                    className="entry-actions"
                                    role="group"
                                    aria-label="Entry actions"
                                  >
                                    <button
                                      type="button"
                                      aria-label="Assign trip or group"
                                      aria-pressed={tripEntry?.id === row.id}
                                      disabled={
                                        saving ||
                                        spendingStore.busy ||
                                        !row.is_selected ||
                                        effective.entry_type === "payment"
                                      }
                                      onClick={(event) => {
                                        tripTrigger.current =
                                          event.currentTarget;
                                        setEditing(null);
                                        setReviewing(null);
                                        setSelected(null);
                                        setNotice("");
                                        setDescribing(null);
                                        setTripEntry({ ...row });
                                      }}
                                    >
                                      Trip / group
                                    </button>
                                    <button
                                      type="button"
                                      disabled={saving || !row.is_selected}
                                      aria-pressed={describing?.id === row.id}
                                      onClick={(event) => {
                                        descriptionTrigger.current =
                                          event.currentTarget;
                                        setEditing(null);
                                        setTripEntry(null);
                                        setReviewing(null);
                                        setSelected(null);
                                        setNotice("");
                                        setDescribing({ ...row });
                                      }}
                                    >
                                      Edit description
                                    </button>
                                    <button
                                      type="button"
                                      className="evidence-link"
                                      aria-label="View evidence"
                                      aria-pressed={selected?.id === row.id}
                                      disabled={saving}
                                      onClick={(event) => {
                                        evidenceTrigger.current =
                                          event.currentTarget;
                                        setDescribing(null);
                                        setEditing(null);
                                        setTripEntry(null);
                                        setReviewing(null);
                                        setNotice("");
                                        setSelected({ ...row });
                                      }}
                                    >
                                      View
                                    </button>
                                    <button
                                      type="button"
                                      aria-label="Edit entry"
                                      aria-pressed={editing?.id === row.id}
                                      disabled={
                                        saving ||
                                        !row.is_selected ||
                                        labelStore.loading ||
                                        !!labelStore.error
                                      }
                                      onClick={(event) => {
                                        editTrigger.current =
                                          event.currentTarget;
                                        setDescribing(null);
                                        setReviewing(null);
                                        setSelected(null);
                                        setNotice("");
                                        setTripEntry(null);
                                        setEditing({ ...row });
                                      }}
                                    >
                                      Assign
                                    </button>
                                    <button
                                      type="button"
                                      aria-label="Review entry"
                                      aria-pressed={reviewing?.id === row.id}
                                      disabled={
                                        saving ||
                                        !row.is_selected ||
                                        (!!api &&
                                          row.effective_entry_type ===
                                            undefined)
                                      }
                                      onClick={(event) => {
                                        reviewTrigger.current =
                                          event.currentTarget;
                                        setDescribing(null);
                                        setEditing(null);
                                        setSelected(null);
                                        setNotice("");
                                        setTripEntry(null);
                                        setReviewing({ ...row });
                                      }}
                                    >
                                      Review
                                    </button>
                                  </div>
                                  {notice && (
                                    <p role="status" className="demo-notice">
                                      {notice}
                                    </p>
                                  )}
                                  {tripEntry?.id === row.id && (
                                    <EntryTripEditor
                                      key={tripEntry.id}
                                      entry={tripEntry}
                                      store={spendingStore}
                                      onClose={() => {
                                        setTripEntry(null);
                                        tripTrigger.current?.focus({
                                          preventScroll: true,
                                        });
                                      }}
                                      onSaved={() => {
                                        setTripEntry(null);
                                        setNotice(
                                          "Trip assignment saved. Account and category are unchanged.",
                                        );
                                        tripTrigger.current?.focus({
                                          preventScroll: true,
                                        });
                                      }}
                                    />
                                  )}
                                  {describing?.id === row.id && (
                                    <FriendlyDescriptionEditor
                                      key={describing.id}
                                      row={describing}
                                      onSave={(description) =>
                                        saveEntry(() =>
                                          saveDescription(description),
                                        )
                                      }
                                      onClose={() => {
                                        setDescribing(null);
                                        descriptionTrigger.current?.focus({
                                          preventScroll: true,
                                        });
                                      }}
                                    />
                                  )}
                                  {reviewing?.id === row.id && (
                                    <ReviewEditor
                                      key={reviewing.id}
                                      row={reviewing}
                                      onSave={(save) =>
                                        saveEntry(() => saveReview(save))
                                      }
                                      onClose={() => {
                                        setDescribing(null);
                                        setReviewing(null);
                                        reviewTrigger.current?.focus({
                                          preventScroll: true,
                                        });
                                      }}
                                    />
                                  )}
                                  {editing?.id === row.id && (
                                    <AssignmentEditor
                                      key={editing.id}
                                      row={editing}
                                      labels={labelStore.labels}
                                      onSave={(patch) =>
                                        saveEntry(() => saveAssignments(patch))
                                      }
                                      onClose={() => {
                                        setDescribing(null);
                                        setEditing(null);
                                        editTrigger.current?.focus({
                                          preventScroll: true,
                                        });
                                      }}
                                    />
                                  )}
                                  {selected?.id === row.id && (
                                    <Evidence
                                      key={selected.id}
                                      row={selected}
                                      api={api}
                                      onClose={() => {
                                        setSelected(null);
                                        evidenceTrigger.current?.focus({
                                          preventScroll: true,
                                        });
                                      }}
                                    />
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
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
                      resetDetails();
                    }}
                  >
                    Previous
                  </button>
                  <button
                    disabled={loading || offset + 50 >= total}
                    onClick={() => {
                      setOffset((n) => n + 50);
                      resetDetails();
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
            {notice &&
              !loading &&
              !rows.some((row) => row.id === expandedId) && (
                <p role="status" className="demo-notice">
                  {notice}
                </p>
              )}
          </section>
        )}
      </main>
    </div>
  );
}
