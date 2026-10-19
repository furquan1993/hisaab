import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import type { BrowserClient } from "./client";
import type { Entry } from "./domain";
import type { Label } from "./useLabels";
import { readFunding } from "./funding-client";
import {
  cents,
  decimalText,
  demoFundingGroups,
  fundingMoney,
  type Confirmation,
  type Contribution,
  type FundingAttention,
  type FundingGroup,
  type FundingScope,
} from "./funding-domain";
import FundingDetail from "./FundingDetail";
import FundingEntries from "./FundingEntries";

export default function Reconciliation({
  api,
  ownerId,
  month,
  onMonth,
  demoRows,
  labels,
  receipts,
  confirmations,
  onReceipt,
  onConfirm,
  onEntries,
  onImports,
  onBusyChange,
}: {
  api: BrowserClient | null;
  ownerId?: string;
  month: string;
  onMonth: (month: string) => void;
  demoRows: Entry[];
  labels: Label[];
  receipts: Contribution[];
  confirmations: Confirmation[];
  onReceipt: (receipt: Contribution) => void;
  onConfirm: (confirmation: Confirmation) => void;
  onEntries: () => void;
  onImports: () => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const [live, setLive] = useState<FundingGroup[]>([]),
    [attention, setAttention] = useState<FundingAttention[]>([]),
    [loading, setLoading] = useState(!!api),
    [error, setError] = useState("");
  const [loadedMonth, setLoadedMonth] = useState("");
  const [refresh, setRefresh] = useState(0),
    [expanded, setExpanded] = useState<string | null>(null),
    [active, setActive] = useState<
      (FundingScope & { card_label: string; account_name: string }) | null
    >(null),
    [locked, setLocked] = useState(false);
  const demo = useMemo(
    () => demoFundingGroups(demoRows, labels, receipts, confirmations),
    [demoRows, labels, receipts, confirmations],
  );
  const overviewHeading = useRef<HTMLHeadingElement>(null);
  const accountToggle = useRef<HTMLButtonElement>(null);
  const triggerId = (
    g: Pick<FundingGroup, "card_id" | "account_id" | "currency" | "month">,
  ) => ["funding-open", g.card_id, g.account_id, g.currency, g.month].join("-");
  const date = month + "-01";
  useEffect(() => {
    if (!api) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setAttention([]);
    readFunding(api, date, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setLive(result.groups);
          setLoadedMonth(date);
          setAttention(result.attention);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          setLive([]);
          setError(
            e instanceof Error ? e.message : "Could not load reconciliation.",
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, date, refresh]);
  const groups = (api ? (loadedMonth === date ? live : []) : demo).filter(
    (g) =>
      !g.month ||
      g.month === date ||
      (g.month < date &&
        (cents(g.outstanding) > 0n || cents(g.credit) > 0n || g.needs_review)),
  );
  useEffect(() => {
    if (
      active &&
      !loading &&
      !groups.some(
        (g) =>
          g.card_id === active.card_id &&
          g.account_id === active.account_id &&
          g.currency === active.currency &&
          g.month === active.month,
      )
    ) {
      setActive(null);
      (accountToggle.current ?? overviewHeading.current)?.focus({
        preventScroll: true,
      });
    }
  }, [active, groups, loading]);
  const summaries = new Map<
    string,
    { account: string; currency: string | null; groups: FundingGroup[] }
  >();
  for (const group of groups) {
    const key = JSON.stringify([group.account_id, group.currency]);
    const summary = summaries.get(key) ?? {
      account: group.account_name ?? "Unassigned",
      currency: group.currency,
      groups: [],
    };
    summary.groups.push(group);
    summaries.set(key, summary);
  }
  function onBusy(busy: boolean) {
    setLocked(busy);
    onBusyChange(busy);
  }
  return (
    <section className="page reconciliation-page">
      <span className="eyebrow">MONTHLY RECONCILIATION</span>
      <h1 ref={overviewHeading} tabIndex={-1}>
        Accounts, in balance.
      </h1>
      <p>
        Monthly account totals across available cards. Contributions are per
        card/account/currency, with arrears attributed to their original
        statement month. Card repayments are excluded.
      </p>
      <div className="form-actions">
        <label className="funding-label">
          Reconciliation month
          <input
            aria-label="Reconciliation month"
            type="month"
            required
            value={month}
            disabled={locked}
            onChange={(e) => {
              if (/^\d{4}-\d{2}$/.test(e.target.value)) {
                onMonth(e.target.value);
                setActive(null);
                setExpanded(null);
              }
            }}
          />
        </label>
        <button
          type="button"
          disabled={locked || loading}
          onClick={() => setRefresh((n) => n + 1)}
        >
          Reload reconciliation
        </button>
        <button type="button" disabled={locked} onClick={onEntries}>
          Review entries and assignments
        </button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {loading && <p role="status">Loading reconciliation…</p>}
      {!!attention.length && (
        <div className="notice">
          <p>{attention.length} statement source(s) need attention.</p>
          <button type="button" disabled={locked} onClick={onImports}>
            Review Imports
          </button>
          <ul>
            {attention.map((a) => (
              <li key={a.id}>
                {a.card_label}: {a.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      {!api && (
        <p className="demo-notice">
          Synthetic demo. Contributions and confirmations are memory-only and
          reset on reload or exit.
        </p>
      )}
      <section className="ledger" aria-label="Monthly account summary">
        <div className="table-scroll">
          <table>
            <caption>Account summary · {month}</caption>
            <thead>
              <tr>
                <th>Budget account</th>
                <th>Currency</th>
                <th>Net spending this month</th>
                <th>Contributed to this month</th>
                <th>Pending this month</th>
                <th>Earlier months pending</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {[...summaries]
                .sort(
                  (a, b) =>
                    a[1].account.localeCompare(b[1].account) ||
                    (a[1].currency ?? "").localeCompare(b[1].currency ?? ""),
                )
                .map(([key, summary]) => {
                  const sum = (
                    field: "net" | "received" | "outstanding",
                    current: boolean,
                  ) =>
                    decimalText(
                      summary.groups
                        .filter((g) =>
                          current
                            ? g.month === date
                            : !!g.month && g.month < date,
                        )
                        .reduce((s, g) => s + cents(g[field]), 0n),
                    );
                  const issues = summary.groups.some(
                    (g) => g.blocked || g.needs_review,
                  );
                  return (
                    <Fragment key={key}>
                      <tr
                        className={
                          "entry-row" + (expanded === key ? " expanded" : "")
                        }
                        onClick={(event) => {
                          if (
                            !locked &&
                            !(event.target as HTMLElement).closest("button")
                          ) {
                            setExpanded(expanded === key ? null : key);
                            setActive(null);
                          }
                        }}
                      >
                        <td>
                          <button
                            type="button"
                            className="funding-account"
                            title={summary.account}
                            ref={expanded === key ? accountToggle : undefined}
                            disabled={locked}
                            aria-label={`View cards for ${summary.account} (${summary.currency ?? "?"})`}
                            aria-expanded={expanded === key}
                            onClick={() => {
                              setExpanded(expanded === key ? null : key);
                              setActive(null);
                            }}
                          >
                            <span aria-hidden="true">
                              {expanded === key ? "▾" : "▸"}
                            </span>
                            <span>{summary.account}</span>
                          </button>
                        </td>
                        <td>{summary.currency ?? "Unknown"}</td>
                        <td>
                          {fundingMoney(sum("net", true), summary.currency)}
                        </td>
                        <td>
                          {fundingMoney(
                            sum("received", true),
                            summary.currency,
                          )}
                        </td>
                        <td>
                          {fundingMoney(
                            sum("outstanding", true),
                            summary.currency,
                          )}
                        </td>
                        <td>
                          {fundingMoney(
                            sum("outstanding", false),
                            summary.currency,
                          )}
                        </td>
                        <td>
                          {issues
                            ? "Needs attention"
                            : summary.groups.some(
                                  (g) => cents(g.outstanding) > 0n,
                                )
                              ? "Pending"
                              : summary.groups.some(
                                    (g) => cents(g.received) > 0n,
                                  )
                                ? "Settled"
                                : "No contribution due"}
                        </td>
                      </tr>
                      {expanded === key && (
                        <tr>
                          <td colSpan={7}>
                            <div className="funding-card-list">
                              {summary.groups
                                .sort(
                                  (a, b) =>
                                    a.card_label.localeCompare(b.card_label) ||
                                    (a.month ?? "").localeCompare(
                                      b.month ?? "",
                                    ),
                                )
                                .map((g) => (
                                  <section
                                    key={JSON.stringify([g.card_id, g.month])}
                                    className="funding-card"
                                  >
                                    <h3>
                                      {g.card_label} ·{" "}
                                      {g.month?.slice(0, 7) ?? "Month unknown"}
                                    </h3>
                                    <p>
                                      Net: {fundingMoney(g.net, g.currency)} ·
                                      Contributed:{" "}
                                      {fundingMoney(g.received, g.currency)} ·
                                      Outstanding:{" "}
                                      {fundingMoney(g.outstanding, g.currency)}{" "}
                                      · Credit:{" "}
                                      {fundingMoney(g.credit, g.currency)}
                                    </p>
                                    <p>
                                      {g.blocked
                                        ? "Source issues or missing assignments. Review this card's entries/imports first."
                                        : g.needs_review
                                          ? "Needs review after changes; recorded contributions are preserved."
                                          : cents(g.outstanding) > 0n
                                            ? "Pending contribution"
                                            : cents(g.received) > 0n
                                              ? "Settled"
                                              : "No contribution due"}
                                    </p>
                                    <button
                                      type="button"
                                      id={triggerId(g)}
                                      disabled={
                                        locked ||
                                        !g.account_id ||
                                        !g.currency ||
                                        !g.month
                                      }
                                      onClick={() =>
                                        setActive({
                                          card_id: g.card_id,
                                          account_id: g.account_id!,
                                          currency: g.currency!,
                                          month: g.month!,
                                          card_label: g.card_label,
                                          account_name: summary.account,
                                        })
                                      }
                                    >
                                      Contributions for {g.card_label} ·{" "}
                                      {g.month?.slice(0, 7) ?? "Unknown"}
                                    </button>
                                    <FundingEntries
                                      api={api}
                                      group={g}
                                      demoRows={demoRows}
                                    />
                                    {active &&
                                      active.card_id === g.card_id &&
                                      active.month === g.month &&
                                      active.account_id === g.account_id &&
                                      active.currency === g.currency && (
                                        <FundingDetail
                                          key={JSON.stringify(active)}
                                          api={api}
                                          ownerId={ownerId}
                                          scope={active}
                                          cardLabel={active.card_label}
                                          accountName={active.account_name}
                                          demoGroups={demo}
                                          demoReceipts={receipts}
                                          onDemoReceipt={onReceipt}
                                          onDemoConfirm={onConfirm}
                                          onChanged={() =>
                                            setRefresh((n) => n + 1)
                                          }
                                          onClose={() => {
                                            setActive(null);
                                            document
                                              .getElementById(triggerId(active))
                                              ?.focus({ preventScroll: true });
                                          }}
                                          onBusyChange={onBusy}
                                        />
                                      )}
                                  </section>
                                ))}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
            </tbody>
          </table>
        </div>
        {!loading && !error && !summaries.size && (
          <p className="empty">
            No spending or outstanding contributions for this month. Other cards
            do not need to have generated statements.
          </p>
        )}
      </section>
      <p className="page-foot">
        Negative totals and over-contribution credits remain visible. They are
        not automatically offset across months, cards or currencies. No money is
        moved.
      </p>
    </section>
  );
}
