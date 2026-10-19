import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Entry } from "./domain";
import type { Label } from "./useLabels";
export type AssignmentPatch = {
  category_id: string | null;
  account_id: string | null;
};

export default function AssignmentEditor({
  row,
  labels,
  onSave,
  onClose,
}: {
  row: Entry;
  labels: Label[];
  onSave: (patch: AssignmentPatch) => Promise<void>;
  onClose: () => void;
}) {
  const [category, setCategory] = useState(row.category_id ?? "");
  const [account, setAccount] = useState(row.account_id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, [row]);
  function options(kind: Label["kind"], current: string) {
    return labels
      .filter((l) => l.kind === kind && (!l.is_archived || l.id === current))
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((l) => (
        <option key={l.id} value={l.id}>
          {l.name}
          {l.is_archived ? " (archived)" : ""}
        </option>
      ));
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onSave({
        category_id: category || null,
        account_id: account || null,
      });
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not confirm the save. Reload before retrying.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <aside className="evidence" aria-label="Entry decisions">
      <div className="section-head">
        <div>
          <span className="eyebrow">YOUR DECISIONS · SOURCE UNCHANGED</span>
          <h2 ref={heading} tabIndex={-1}>
            {row.description}
          </h2>
        </div>
        <button
          type="button"
          disabled={busy}
          aria-label="Close entry editor"
          onClick={onClose}
        >
          Close
        </button>
      </div>
      <form className="decision-form" onSubmit={submit}>
        <p>
          Account is the funding pot. Category describes the entry. Both are
          optional and independent.
        </p>
        {row.needs_review && (
          <p className="demo-notice">
            Assigning labels does not resolve this entry’s source issues.
          </p>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <fieldset disabled={busy}>
          <div className="decision-columns">
            <label>
              Account
              <select
                aria-label="Account"
                value={account}
                onChange={(e) => setAccount(e.target.value)}
              >
                <option value="">Unassigned</option>
                {options("account", account)}
              </select>
            </label>
            <label>
              Category
              <select
                aria-label="Category"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                <option value="">Unassigned</option>
                {options("category", category)}
              </select>
            </label>
          </div>
          <div className="form-actions">
            <button type="submit">
              {busy ? "Saving…" : "Save assignments"}
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
