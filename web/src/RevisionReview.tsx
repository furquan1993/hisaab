import { useEffect, useRef, useState, type ReactNode } from "react";
import { formatAmount, type Entry } from "./domain";
import type { IdentityMapping, Revision, Source } from "./revisions-client";

export function SourceTable({
  title,
  rows,
  identity,
  onEvidence,
}: {
  title: string;
  rows: Entry[];
  identity?: (row: Entry) => ReactNode;
  onEvidence: (row: Entry, trigger: HTMLButtonElement) => void;
}) {
  return (
    <section className="ledger" aria-label={title}>
      <div className="ledger-heading">
        <h3>{title}</h3>
        <span>{rows.length} entries</span>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Row</th>
              <th>Extracted transaction</th>
              <th>Date</th>
              <th>Type</th>
              <th>Amount</th>
              {identity && <th>Identity decision</th>}
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.sequence}</td>
                <td>{row.description}</td>
                <td>{row.transaction_date ?? "Unknown"}</td>
                <td>{row.entry_type}</td>
                <td className="amount">
                  {formatAmount(row.amount, row.currency, row.direction)}
                </td>
                {identity && <td>{identity(row)}</td>}
                <td>
                  <button
                    type="button"
                    onClick={(event) => onEvidence(row, event.currentTarget)}
                  >
                    View evidence
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!rows.length && (
        <p className="empty">No extracted entries in this source.</p>
      )}
    </section>
  );
}

export default function RevisionReview({
  revision,
  entries,
  sources,
  onAccept,
  onReject,
  onClose,
  onEvidence,
}: {
  revision: Revision;
  entries: Entry[];
  sources: Source[];
  onAccept: (
    mapping: IdentityMapping[],
    removed: string[],
    reason: string,
    ackMetadata: boolean,
  ) => Promise<void>;
  onReject: (reason: string) => Promise<void>;
  onClose: () => void;
  onEvidence: (row: Entry, trigger: HTMLButtonElement) => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [ackRemoved, setAckRemoved] = useState(false),
    [ackMetadata, setAckMetadata] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    heading.current?.focus();
  }, [revision.id]);
  const before = entries.filter(
    (row) => row.import_id === revision.base_import_id,
  );
  const after = entries.filter(
    (row) => row.import_id === revision.candidate_import_id,
  );
  const autoOld = new Set(
    revision.plan.matches.map((pair) => pair.previous_entry_id),
  );
  const used = new Set([
    ...autoOld,
    ...Object.values(choices).filter((id) => id && id !== "new"),
  ]);
  const removed = before
    .filter((row) => !used.has(row.id))
    .map((row) => row.id);
  const undecided = revision.plan.unmatched_new.some((id) => !choices[id]);
  async function accept() {
    setError("");
    if (
      !reason.trim() ||
      undecided ||
      (removed.length > 0 && !ackRemoved) ||
      (revision.plan.metadata_changed && !ackMetadata)
    ) {
      setError(
        "Decide every uncertain identity, acknowledge removals and metadata changes, and provide a reason.",
      );
      return;
    }
    setBusy(true);
    try {
      await onAccept(
        revision.plan.unmatched_new.map((id) => ({
          new_entry_id: id,
          previous_entry_id: choices[id] === "new" ? null : choices[id],
        })),
        removed,
        reason.trim(),
        ackMetadata,
      );
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not confirm acceptance. Reload before retrying.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function reject() {
    if (!reason.trim()) {
      setError("Provide a reason for rejecting this candidate.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onReject(reason.trim());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not confirm rejection.");
    } finally {
      setBusy(false);
    }
  }
  function identity(row: Entry) {
    const pair = revision.plan.matches.find(
      (pair) => pair.new_entry_id === row.id,
    );
    if (pair)
      return (
        <span>
          Retains published row{" "}
          {before.find((old) => old.id === pair.previous_entry_id)?.sequence}
        </span>
      );
    return (
      <select
        aria-label={"Identity for candidate row " + row.sequence}
        value={choices[row.id] ?? ""}
        disabled={busy}
        onChange={(event) => {
          setChoices((current) => ({
            ...current,
            [row.id]: event.target.value,
          }));
          setAckRemoved(false);
        }}
      >
        <option value="">Choose identity…</option>
        <option value="new">New logical entry</option>
        {before
          .filter((old) => !autoOld.has(old.id))
          .map((old) => (
            <option
              key={old.id}
              value={old.id}
              disabled={used.has(old.id) && choices[row.id] !== old.id}
            >
              Published row {old.sequence} · {old.description} ·{" "}
              {formatAmount(old.amount, old.currency, old.direction)}
            </option>
          ))}
      </select>
    );
  }
  return (
    <aside className="revision-review" aria-label="Revision comparison">
      <div className="section-head">
        <div>
          <span className="eyebrow">EXPLICIT SOURCE REVIEW</span>
          <h2 ref={heading} tabIndex={-1}>
            Compare statement sources
          </h2>
        </div>
        <button type="button" disabled={busy} onClick={onClose}>
          Close comparison
        </button>
      </div>
      <p className="view-help">
        Original extracted values are shown. Unique unchanged evidence retains
        its logical identity. Reorders, splits, merges and uncertain matches
        need your explicit decision. Removed rows and their decisions remain in
        history.
      </p>
      <div className="source-metadata">
        {[revision.base_import_id, revision.candidate_import_id].map(
          (id, index) => {
            const source = sources.find((source) => source.id === id);
            return (
              <div key={id ?? "none"}>
                <h3>
                  {index === 0 ? "Published version" : "Candidate version"}
                </h3>
                <p>{source?.source_filename ?? "No published source"}</p>
                {source && (
                  <small>
                    Printed date: {source.parsed_statement_date ?? "unknown"} ·{" "}
                    {source.page_count} pages · Parser {source.parser_version} ·
                    Extractor {source.extractor_version}
                  </small>
                )}
              </div>
            );
          },
        )}
      </div>
      <SourceTable
        title="Published extraction"
        rows={before}
        onEvidence={onEvidence}
      />
      <SourceTable
        title="Candidate extraction"
        rows={after}
        identity={identity}
        onEvidence={onEvidence}
      />
      <div className="decision-form">
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {removed.length > 0 && (
          <label className="check-label">
            <input
              type="checkbox"
              checked={ackRemoved}
              disabled={busy}
              onChange={(event) => setAckRemoved(event.target.checked)}
            />
            I reviewed the {removed.length} removed rows; their decisions stay
            in history.
          </label>
        )}
        {revision.plan.metadata_changed && (
          <label className="check-label">
            <input
              type="checkbox"
              checked={ackMetadata}
              disabled={busy}
              onChange={(event) => setAckMetadata(event.target.checked)}
            />
            I reviewed the changed statement metadata. Source date conflicts
            still need review.
          </label>
        )}
        <label>
          Revision reason
          <textarea
            value={reason}
            maxLength={2000}
            disabled={busy}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        <div className="form-actions">
          <button type="button" disabled={busy} onClick={() => void accept()}>
            {busy ? "Saving…" : "Accept reviewed source"}
          </button>
          <button
            type="button"
            disabled={busy}
            className="quiet"
            onClick={() => void reject()}
          >
            Reject candidate
          </button>
        </div>
      </div>
    </aside>
  );
}
