import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Source } from "./revisions-client";
import { criticalIssues, issueKey } from "./review-domain";
export type StatementReviewSave = {
  acknowledged: string[];
  date: string | null;
  reason: string;
};
export default function StatementReview({
  source,
  onSave,
  onClose,
}: {
  source: Source;
  onSave: (save: StatementReviewSave) => Promise<void>;
  onClose: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const [ack, setAck] = useState(source.import_acknowledged);
  const [date, setDate] = useState(source.statement_date_override ?? "");
  const [reason, setReason] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    heading.current?.focus();
  }, [source.id]);
  const warnings = [
    ...new Map(
      source.issues
        .filter(
          (issue) =>
            !criticalIssues.has(issue.code) &&
            ![
              "competing_statement_file",
              "ambiguous_statement_match",
              "statement_match_unresolved",
            ].includes(issue.code),
        )
        .map((issue) => [issueKey(issue), issue]),
    ).values(),
  ];
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!reason.trim()) {
      setError("Explain the statement review.");
      return;
    }
    setBusy(true);
    try {
      await onSave({
        acknowledged: ack,
        date: date || null,
        reason: reason.trim(),
      });
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not confirm the statement review.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <aside className="evidence" aria-label="Statement review">
      <div className="section-head">
        <div>
          <span className="eyebrow">STATEMENT-LEVEL REVIEW</span>
          <h2 ref={heading} tabIndex={-1}>
            Review {source.card_label} statement
          </h2>
        </div>
        <button type="button" disabled={busy} onClick={onClose}>
          Close statement review
        </button>
      </div>
      <form className="decision-form" onSubmit={submit}>
        <p>
          Only acknowledge coverage after checking the original and confirming
          that no transactions are missing. Otherwise leave the warning pending
          and correct the import.
        </p>
        {source.import_review_stale && (
          <p className="notice">
            Earlier statement acknowledgements refer to different evidence and
            are preserved but not applied. Review this source afresh.
          </p>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <fieldset disabled={busy}>
          <label>
            Corrected statement date (optional)
            <input
              aria-label="Corrected statement date (optional)"
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
            <small>
              Extracted: {source.parsed_statement_date ?? "Unknown"}. This is
              the bill date, not its payment due date. Blank restores the
              extracted value.
            </small>
          </label>
          {warnings.map((issue) => (
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
              I verified complete coverage for {issue.code.replaceAll("_", " ")}
              {issue.page ? " on page " + String(issue.page) : ""}
            </label>
          ))}
          {!warnings.length && (
            <p>
              No acknowledgeable coverage warnings on this extraction. Missing
              or conflicting dates require a verified date correction.
            </p>
          )}
          <label>
            Statement review reason
            <textarea
              required
              maxLength={2000}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          <div className="form-actions">
            <button type="submit">
              {busy ? "Saving…" : "Save statement review"}
            </button>
            <button type="button" className="quiet" onClick={onClose}>
              Cancel
            </button>
          </div>
        </fieldset>
      </form>
    </aside>
  );
}
