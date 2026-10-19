import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Entry } from "./domain";

export default function FriendlyDescriptionEditor({
  row,
  onSave,
  onClose,
}: {
  row: Entry;
  onSave: (description: string | null) => Promise<void>;
  onClose: () => void;
}) {
  const [value, setValue] = useState(row.friendly_description ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onSave(value.trim() || null);
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Could not save the description.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <aside className="evidence" aria-label="Friendly description editor">
      <div className="section-head">
        <h2 ref={heading} tabIndex={-1}>
          Friendly description
        </h2>
        <button type="button" disabled={busy} onClick={onClose}>
          Close
        </button>
      </div>
      <p>Statement description: {row.description}</p>
      <form className="decision-form" onSubmit={submit}>
        <p>
          Describe what you bought. Leave blank to use the statement
          description.
        </p>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <fieldset disabled={busy}>
          <label>
            Friendly description
            <input
              value={value}
              maxLength={500}
              onChange={(event) => setValue(event.target.value)}
            />
          </label>
          <div className="form-actions">
            <button type="submit">
              {busy ? "Saving…" : "Save description"}
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
