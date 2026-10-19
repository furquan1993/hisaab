import { useEffect, useRef, useState, type FormEvent } from "react";
import type { BrowserClient } from "./client";
import {
  FundingError,
  confirmFunding,
  loadFundingDetail,
  recordContribution,
} from "./funding-client";
import {
  cents,
  decimalText,
  demoContribution,
  demoPreview,
  fundingMoney,
  sameScope,
  type Confirmation,
  type Contribution,
  type ContributionDraft,
  type FundingGroup,
  type FundingPreview,
  type FundingScope,
} from "./funding-domain";

export default function FundingDetail({
  api,
  ownerId,
  scope,
  cardLabel,
  accountName,
  demoGroups,
  demoReceipts,
  onDemoReceipt,
  onDemoConfirm,
  onChanged,
  onClose,
  onBusyChange,
}: {
  api: BrowserClient | null;
  ownerId?: string;
  scope: FundingScope;
  cardLabel: string;
  accountName: string;
  demoGroups: FundingGroup[];
  demoReceipts: Contribution[];
  onDemoReceipt: (receipt: Contribution) => void;
  onDemoConfirm: (confirmation: Confirmation) => void;
  onChanged: () => void;
  onClose: () => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const [data, setData] = useState<{
    preview: FundingPreview;
    history: Contribution[];
  } | null>(null);
  const [reload, setReload] = useState(0),
    [loading, setLoading] = useState(!!api),
    [busy, setBusy] = useState(false);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [amount, setAmount] = useState(""),
    [note, setNote] = useState(""),
    [reason, setReason] = useState("");
  const [receivedOn, setReceivedOn] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  });
  const pending = useRef<{ draft: ContributionDraft; token: string } | null>(
    null,
  );
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, [scope]);
  useEffect(() => {
    if (!api) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setData(null);
    if (!ownerId) {
      setError("Reload your signed-in workspace.");
      setLoading(false);
      return;
    }
    loadFundingDetail(api, scope, ownerId, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setData(result);
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            "Could not load contribution balances/history. Reload before contributing.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, ownerId, scope, reload]);
  const preview = api ? data?.preview : demoPreview(demoGroups, scope);
  const history = api
    ? (data?.history ?? [])
    : demoReceipts.filter((r) => sameScope(r, scope));
  const outstanding =
    preview?.groups.reduce((sum, g) => sum + cents(g.outstanding), 0n) ?? 0n;
  const blocked =
    !preview || preview.groups.some((g) => g.blocked || g.needs_review);
  const locked = busy || !!pending.current;
  function lock(value: boolean) {
    setBusy(value);
    onBusyChange(value);
  }
  async function contribute(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!preview) return;
    setError("");
    setNotice("");
    const full =
      (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") ===
      "full";
    if (!pending.current) {
      try {
        if (!full && (cents(amount) <= 0n || cents(amount) > outstanding))
          throw Error(
            "Enter a positive amount no greater than the outstanding balance.",
          );
      } catch (e) {
        setError(
          e instanceof Error ? e.message : "Enter a valid decimal amount.",
        );
        return;
      }
      pending.current = {
        draft: {
          id: crypto.randomUUID(),
          amount: full ? null : decimalText(cents(amount)),
          received_on: receivedOn,
          note,
        },
        token: preview.token,
      };
    }
    lock(true);
    try {
      const request = pending.current;
      if (api) {
        if (!ownerId)
          throw new FundingError("Reload your signed-in workspace.");
        await recordContribution(
          api,
          scope,
          request.draft,
          request.token,
          ownerId,
        );
      } else
        onDemoReceipt(
          demoContribution(demoGroups, scope, request.draft, request.token),
        );
      pending.current = null;
      setAmount("");
      setNote("");
      setNotice(
        "Contribution recorded against its original statement month(s).",
      );
      setReload((n) => n + 1);
      onChanged();
      heading.current?.focus({ preventScroll: true });
    } catch (e) {
      if (e instanceof FundingError || !api) pending.current = null;
      setError(
        (e instanceof Error
          ? e.message
          : "Could not confirm the contribution.") +
          (pending.current
            ? " Retry the same request below; do not record another contribution for this payment."
            : ""),
      );
    } finally {
      setBusy(false);
      onBusyChange(!!pending.current);
    }
  }
  async function confirm(month: string) {
    if (!preview || !reason.trim()) {
      setError("Provide a reason for confirming the revised balance.");
      return;
    }
    setError("");
    setNotice("");
    lock(true);
    try {
      if (api) {
        if (!ownerId) throw Error("Reload your signed-in workspace.");
        await confirmFunding(
          api,
          { ...scope, month },
          reason,
          preview.token,
          ownerId,
          scope.month,
        );
      } else {
        const group = preview.groups.find((g) => g.month === month)!;
        onDemoConfirm({
          ...scope,
          month,
          fingerprint: group.fingerprint,
          created_at: new Date().toISOString(),
        });
      }
      setReason("");
      setNotice(
        "Revised balance confirmed. Previous contributions are unchanged.",
      );
      setReload((n) => n + 1);
      onChanged();
      heading.current?.focus({ preventScroll: true });
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not confirm the review.",
      );
    } finally {
      lock(false);
    }
  }
  return (
    <section className="funding-detail" aria-label="Contributions and balances">
      <div className="section-head">
        <div>
          <span className="eyebrow">PER CARD · ORIGINAL MONTH RETAINED</span>
          <h2 ref={heading} tabIndex={-1}>
            {cardLabel} · {accountName} · {scope.currency}
          </h2>
        </div>
        <button type="button" disabled={locked} onClick={onClose}>
          Close contributions
        </button>
      </div>
      <p>
        Outstanding through {scope.month.slice(0, 7)}. Contributions clear the
        oldest month first, on this card and account only. This records funding
        received, not payment of the card bill.
      </p>
      {loading && <p role="status">Loading balances and history…</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <button
        type="button"
        disabled={locked || loading}
        onClick={() => setReload((n) => n + 1)}
      >
        Reload balances
      </button>
      {preview && (
        <>
          <div className="table-scroll">
            <table>
              <caption>Original-month balances</caption>
              <thead>
                <tr>
                  <th>Statement month</th>
                  <th>Net spending</th>
                  <th>Contributed</th>
                  <th>Outstanding</th>
                  <th>Over-contribution credit</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {preview.groups.map((g) => (
                  <tr key={g.month}>
                    <td>{g.month.slice(0, 7)}</td>
                    <td>{fundingMoney(g.net, scope.currency)}</td>
                    <td>{fundingMoney(g.received, scope.currency)}</td>
                    <td>{fundingMoney(g.outstanding, scope.currency)}</td>
                    <td>{fundingMoney(g.credit, scope.currency)}</td>
                    <td>
                      <span>
                        {g.blocked
                          ? "Source issues"
                          : g.needs_review
                            ? "Needs review"
                            : cents(g.outstanding) > 0n
                              ? "Pending"
                              : cents(g.received) > 0n
                                ? "Settled"
                                : "No contribution due"}
                      </span>
                      {g.needs_review && !g.blocked && (
                        <button
                          type="button"
                          disabled={locked}
                          onClick={() => confirm(g.month)}
                        >
                          Confirm {g.month.slice(0, 7)}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {preview.groups.some((g) => g.needs_review) && (
            <label className="funding-label">
              Balance review reason
              <input
                maxLength={2000}
                value={reason}
                disabled={locked}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
          )}
          {blocked && (
            <p className="notice">
              Resolve source issues or confirm revised balances before
              contributing. Other cards do not need to be ready.
            </p>
          )}
          <form onSubmit={contribute} className="decision-form">
            <strong>
              Outstanding:{" "}
              {fundingMoney(decimalText(outstanding), scope.currency)}
            </strong>
            <fieldset
              disabled={
                busy || !!pending.current || blocked || outstanding === 0n
              }
            >
              <div className="decision-columns">
                <label>
                  Partial contribution amount
                  <input
                    inputMode="decimal"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                  />
                </label>
                <label>
                  Received on
                  <input
                    type="date"
                    required
                    value={receivedOn}
                    onChange={(e) => setReceivedOn(e.target.value)}
                  />
                </label>
                <label>
                  Contribution note (optional)
                  <input
                    maxLength={2000}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </label>
              </div>
              <div className="form-actions">
                <button type="submit" value="partial">
                  Record partial contribution
                </button>
                <button type="submit" value="full">
                  Settle in full
                </button>
              </div>
            </fieldset>
            {pending.current && (
              <button type="submit" disabled={busy}>
                {busy ? "Recording…" : "Retry same contribution"}
              </button>
            )}
          </form>
        </>
      )}
      <h3>Contribution history</h3>
      {!loading && !history.length && (
        <p>No contributions recorded for this card/account/currency.</p>
      )}
      <ul className="contribution-history">
        {history.map((r) => (
          <li key={r.id}>
            <strong>{fundingMoney(r.amount, r.currency)}</strong> received{" "}
            {r.received_on}
            {r.note && <p>{r.note}</p>}
            <ul>
              {r.applications.map((a) => (
                <li key={a.month}>
                  {a.month.slice(0, 7)}: {fundingMoney(a.amount, r.currency)}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </section>
  );
}
