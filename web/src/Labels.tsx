import DeleteAccount from "./DeleteAccount";
import type { AccountDeletion } from "./account-deletion";
import { compareLabelNames } from "./label-order";
import { useRef, useState, type FormEvent } from "react";
import type { Label, LabelDraft } from "./useLabels";

export default function Labels({
  kind,
  labels,
  loading,
  error,
  onSave,
  onReload,
  onPreviewDelete,
  onDelete,
}: {
  kind: Label["kind"];
  labels: Label[];
  loading: boolean;
  error: string;
  onSave: (draft: LabelDraft) => Promise<Label>;
  onReload: () => void;
  onPreviewDelete: (label: Label) => Promise<AccountDeletion>;
  onDelete: (preview: AccountDeletion) => Promise<void>;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const [deleting, setDeleting] = useState<AccountDeletion | null>(null);
  const deleteTrigger = useRef<HTMLButtonElement | null>(null);
  const [editing, setEditing] = useState<Label | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [notice, setNotice] = useState("");
  const title = kind === "account" ? "Account" : "Category";
  const relevant = labels
    .filter((l) => l.kind === kind)
    .sort((a, b) => compareLabelNames(a.name, b.name));
  async function submit(event: FormEvent) {
    event.preventDefault();
    setFailure("");
    setNotice("");
    if (!name.trim() || name.trim().length > 120) {
      setFailure("Use a name of 1 to 120 characters.");
      return;
    }
    setBusy(true);
    try {
      await onSave({
        id: editing?.id ?? null,
        kind,
        name: name.trim(),
        is_archived: editing?.is_archived ?? false,
        version: editing?.version ?? 0,
      });
      setName("");
      setEditing(null);
      setNotice(title + " saved.");
    } catch (e) {
      setFailure(
        e instanceof Error ? e.message : "Could not confirm the save.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function archive(label: Label) {
    setBusy(true);
    setFailure("");
    setNotice("");
    try {
      await onSave({ ...label, is_archived: !label.is_archived });
      if (editing?.id === label.id) {
        setEditing(null);
        setName("");
      }
      setNotice(
        label.is_archived
          ? "Label restored."
          : "Label archived. Existing assignments are preserved.",
      );
    } catch (e) {
      setFailure(
        e instanceof Error ? e.message : "Could not confirm the change.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function previewDelete(label: Label) {
    setBusy(true);
    setFailure("");
    setNotice("");
    try {
      setDeleting(await onPreviewDelete(label));
    } catch (e) {
      setFailure(
        e instanceof Error
          ? e.message
          : "Could not load affected transactions.",
      );
    } finally {
      setBusy(false);
    }
  }
  function closeDelete() {
    setDeleting(null);
    deleteTrigger.current?.focus();
  }
  return (
    <section className="page label-page">
      {deleting && (
        <DeleteAccount
          preview={deleting}
          onClose={closeDelete}
          onConfirm={async () => {
            await onDelete(deleting);
            if (editing?.id === deleting.account.id) {
              setEditing(null);
              setName("");
            }
            setDeleting(null);
            requestAnimationFrame(() => heading.current?.focus());
            setNotice("Account deleted. Its transactions are now unassigned.");
          }}
        />
      )}
      <span className="eyebrow">YOUR OWN VOCABULARY</span>
      <h1 ref={heading} tabIndex={-1}>
        {kind === "account" ? "Accounts" : "Categories"}
      </h1>
      <p>
        {kind === "account"
          ? "An Account is a budget or funding pot, not a credit card. It is independent of Category."
          : "Categories describe entries. Choosing a Category never selects an Account."}
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {failure && (
        <p role="alert" className="error">
          {failure}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <div className="ledger label-manager">
        <form onSubmit={submit}>
          <h2>{editing ? "Rename " + title : "Create " + title}</h2>
          <fieldset disabled={busy || loading || !!error}>
            <label>
              {title} name
              <input
                value={name}
                maxLength={120}
                required
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <div className="form-actions">
              <button type="submit">
                {busy
                  ? "Saving…"
                  : editing
                    ? "Save changes"
                    : "Create " + title}
              </button>
              {editing && (
                <button
                  type="button"
                  className="quiet"
                  onClick={() => {
                    setEditing(null);
                    setName("");
                    setFailure("");
                  }}
                >
                  Cancel
                </button>
              )}
            </div>
          </fieldset>
        </form>
        <div className="ledger-heading">
          <h2>Saved {kind === "account" ? "Accounts" : "Categories"}</h2>
          <button type="button" disabled={busy || loading} onClick={onReload}>
            Reload labels
          </button>
        </div>
        {loading && <p role="status">Loading labels…</p>}
        {!loading && relevant.length === 0 && (
          <p className="empty">
            No {kind === "account" ? "Accounts" : "Categories"} yet. Create your
            first one above.
          </p>
        )}
        <ul className="label-list">
          {relevant.map((label) => (
            <li key={label.id}>
              <div>
                <strong>{label.name}</strong>
                <small>
                  {label.is_archived
                    ? "Archived · kept for existing assignments"
                    : "Available for assignments"}
                </small>
              </div>
              <div className="form-actions">
                <button
                  type="button"
                  disabled={busy || loading || !!error}
                  aria-label={"Edit " + label.name}
                  onClick={() => {
                    setEditing(label);
                    setName(label.name);
                    setFailure("");
                    setNotice("");
                  }}
                >
                  Edit
                </button>
                <button
                  type="button"
                  disabled={busy || loading || !!error}
                  aria-label={
                    (label.is_archived ? "Restore " : "Archive ") + label.name
                  }
                  onClick={() => void archive(label)}
                >
                  {label.is_archived ? "Restore" : "Archive"}
                </button>
                {kind === "account" && (
                  <button
                    type="button"
                    className="danger"
                    disabled={busy || loading || !!error}
                    aria-label={"Delete " + label.name}
                    onClick={(event) => {
                      deleteTrigger.current = event.currentTarget;
                      void previewDelete(label);
                    }}
                  >
                    Delete
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </div>
      <p className="page-foot">
        Archiving prevents new assignments without deleting past decisions.
      </p>
    </section>
  );
}
