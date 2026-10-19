import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Entry } from "./domain";
import {
  criticalIssues,
  issueKey,
  reviewedValues,
  reviewFields,
  type ReviewField,
  type ReviewPatch,
} from "./review-domain";
export type ReviewSave = {
  patch: ReviewPatch;
  acknowledged: string[];
  reason: string;
  confirmSource: boolean;
};
export default function ReviewEditor({
  row,
  onSave,
  onClose,
}: {
  row: Entry;
  onSave: (save: ReviewSave) => Promise<void>;
  onClose: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const values = reviewedValues(row);
  const [draft, setDraft] = useState<Record<ReviewField, string>>(
    () =>
      Object.fromEntries(
        reviewFields.map((field) => [field, values[field] ?? ""]),
      ) as Record<ReviewField, string>,
  );
  const [reason, setReason] = useState(""),
    [ack, setAck] = useState(row.applied_acknowledged);
  const [confirm, setConfirm] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    heading.current?.focus();
  }, [row]);
  function original(field: ReviewField) {
    return field === "transaction_time"
      ? (row.original_transaction_time ?? null)
      : row[field];
  }
  function input(field: ReviewField, label: string, type = "text") {
    return (
      <label>
        {label}
        <input
          aria-label={label}
          type={type}
          step={type === "time" ? 1 : undefined}
          value={draft[field]}
          inputMode={field === "amount" ? "decimal" : undefined}
          maxLength={
            field === "currency"
              ? 3
              : field === "description"
                ? 2000
                : undefined
          }
          onChange={(event) =>
            setDraft((current) => ({
              ...current,
              [field]:
                field === "currency"
                  ? event.target.value.toUpperCase()
                  : event.target.value,
            }))
          }
        />
        <small>Extracted: {original(field) ?? "Unknown"}</small>
      </label>
    );
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!reason.trim() || (row.review_stale && !confirm)) {
      setError(
        "Provide a reason and explicitly confirm revised evidence when required.",
      );
      return;
    }
    const patch: ReviewPatch = {};
    for (const field of reviewFields) {
      const desired =
        !draft[field].trim() || draft[field] === original(field)
          ? null
          : draft[field].trim();
      if (desired !== (row.applied_overrides[field] ?? null))
        patch[field] = desired;
    }
    setBusy(true);
    try {
      await onSave({
        patch,
        acknowledged: ack,
        reason: reason.trim(),
        confirmSource: confirm,
      });
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not confirm the review. Reload before retrying.",
      );
    } finally {
      setBusy(false);
    }
  }
  const optional = [
    ...new Map(
      row.entry_issues
        .filter((issue) => !criticalIssues.has(issue.code))
        .map((issue) => [issueKey(issue), issue]),
    ).values(),
  ];
  return (
    <aside className="evidence" aria-label="Entry review">
      <div className="section-head">
        <div>
          <span className="eyebrow">REASONED REVIEW · ORIGINALS UNCHANGED</span>
          <h2 ref={heading} tabIndex={-1}>
            Review {row.description}
          </h2>
        </div>
        <button type="button" disabled={busy} onClick={onClose}>
          Close review
        </button>
      </div>
      <form className="decision-form" onSubmit={submit}>
        <p>
          Correct only what you have verified. Blank fields restore extracted
          values. Account and Category assignments are saved separately.
        </p>
        {row.review_stale && (
          <div className="notice">
            <strong>
              Previous corrections refer to different evidence and are not
              applied.
            </strong>
            <details>
              <summary>Preserved previous corrections</summary>
              <pre>{JSON.stringify(row.overrides, null, 2)}</pre>
            </details>
          </div>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <fieldset disabled={busy}>
          <div className="decision-columns">
            {input("transaction_date", "Reviewed transaction date", "date")}
            {input("transaction_time", "Reviewed transaction time", "time")}
            {input("description", "Reviewed description")}
            {input("amount", "Reviewed amount")}
            {input("currency", "Reviewed currency")}
            <label>
              Reviewed direction
              <select
                aria-label="Reviewed direction"
                value={draft.direction}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    direction: event.target.value,
                  }))
                }
              >
                <option value="">Extracted / unknown</option>
                <option value="debit">debit</option>
                <option value="credit">credit</option>
              </select>
              <small>Extracted: {row.direction ?? "Unknown"}</small>
            </label>
            <label>
              Reviewed entry type
              <select
                aria-label="Reviewed entry type"
                value={draft.entry_type}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    entry_type: event.target.value,
                  }))
                }
              >
                {[
                  "purchase",
                  "payment",
                  "refund",
                  "cashback",
                  "fee",
                  "interest",
                  "tax",
                  "reversal",
                  "unknown",
                ].map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
              <small>Extracted: {row.entry_type}</small>
            </label>
          </div>
          {optional.map((issue) => (
            <label className="check-label" key={issueKey(issue)}>
              <input
                type="checkbox"
                checked={ack.includes(issueKey(issue))}
                onChange={(event) =>
                  setAck((current) =>
                    event.target.checked
                      ? [...current, issueKey(issue)]
                      : current.filter((key) => key !== issueKey(issue)),
                  )
                }
              />
              I reviewed {issue.code.replaceAll("_", " ")}
              {issue.page ? " on page " + String(issue.page) : ""}
            </label>
          ))}
          {row.review_stale && (
            <label className="check-label">
              <input
                type="checkbox"
                checked={confirm}
                onChange={(event) => setConfirm(event.target.checked)}
              />
              I reviewed the new evidence. Replace the previous source-bound
              corrections with this review.
            </label>
          )}
          {(row.unresolved_import_issues ?? row.import_issues).length > 0 && (
            <p className="demo-notice">
              Statement coverage warnings remain separate. Review them from
              Imports; correcting this row will not acknowledge them.
            </p>
          )}
          <label>
            Review reason
            <textarea
              required
              maxLength={2000}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          <div className="form-actions">
            <button type="submit">{busy ? "Saving…" : "Save review"}</button>
            <button type="button" className="quiet" onClick={onClose}>
              Cancel
            </button>
          </div>
        </fieldset>
      </form>
    </aside>
  );
}
