import { useState, type FormEvent } from "react";
import type { SpendingGroup } from "./spending-domain";
import type { SpendingStore } from "./useSpending";

export default function SpendingGroupForm({
  group,
  store,
  onSaved,
  onClose,
}: {
  group: SpendingGroup | null;
  store: SpendingStore;
  onSaved: (group: SpendingGroup) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState(group?.name ?? "");
  const [archived, setArchived] = useState(group?.is_archived ?? false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      onSaved(
        await store.saveGroup({
          id: group?.id ?? null,
          name,
          version: group?.version ?? 0,
          is_archived: archived,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the group.");
    }
  }
  return (
    <form
      className="spending-group-form decision-form"
      onSubmit={submit}
      aria-label={group ? "Manage trip or group" : "Create trip or group"}
    >
      <div className="section-head">
        <h2>{group ? "Manage trip or group" : "New trip or group"}</h2>
        <button type="button" disabled={store.busy} onClick={onClose}>
          Close
        </button>
      </div>
      <p>Group related expenses across categories, cards and months.</p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <fieldset disabled={store.busy}>
        <label>
          Group name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={120}
            autoFocus
          />
        </label>
        {group && (
          <label className="check-label">
            <input
              type="checkbox"
              checked={archived}
              onChange={(e) => setArchived(e.target.checked)}
            />
            Archive group · keep its existing entries
          </label>
        )}
        <div className="form-actions">
          <button type="submit">
            {store.busy ? "Saving…" : group ? "Save group" : "Create group"}
          </button>
          <button type="button" disabled={store.busy} onClick={onClose}>
            Cancel
          </button>
        </div>
      </fieldset>
    </form>
  );
}
