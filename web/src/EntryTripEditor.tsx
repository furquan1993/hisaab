import { useState, type FormEvent } from "react";
import type { Entry } from "./domain";
import type { SpendingStore } from "./useSpending";

export default function EntryTripEditor({
  entry,
  store,
  onClose,
  onSaved,
}: {
  entry: Entry;
  store: SpendingStore;
  onClose: () => void;
  onSaved: () => void;
}) {
  const row = store.rows.find((r) => r.id === entry.id);
  const [choice, setChoice] = useState<string | null>(null);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!row) return;
    setError("");
    try {
      await store.assign((choice ?? row.group_id) || null, [row]);
      onSaved();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not save trip assignment.",
      );
    }
  }
  return (
    <aside className="evidence" aria-label="Trip assignment">
      <div className="section-head">
        <h2>Trip or group</h2>
        <button type="button" disabled={store.busy} onClick={onClose}>
          Close
        </button>
      </div>
      <form className="decision-form" onSubmit={submit}>
        <p>
          Keep this expense’s category and funding account while grouping it
          with related spending.
        </p>
        {store.loading && <p role="status">Loading trip assignment…</p>}
        {(error || store.error) && (
          <p role="alert" className="error">
            {error || store.error}
          </p>
        )}
        {!store.loading && !store.error && !row && (
          <p role="alert">
            This entry is no longer available. Reload before assigning a trip.
          </p>
        )}
        <fieldset
          disabled={store.busy || store.loading || !!store.error || !row}
        >
          <label>
            Trip or group
            <select
              aria-label="Entry trip or group"
              value={choice ?? row?.group_id ?? ""}
              onChange={(e) => setChoice(e.target.value)}
            >
              <option value="">Ungrouped</option>
              {store.groups
                .filter((g) => !g.is_archived || g.id === row?.group_id)
                .map((g) => (
                  <option key={g.id} value={g.id} disabled={g.is_archived}>
                    {g.name}
                    {g.is_archived ? " (archived)" : ""}
                  </option>
                ))}
            </select>
          </label>
          {!store.groups.some((g) => !g.is_archived) && (
            <p>
              Create a trip or group from Spending to start grouping expenses.
            </p>
          )}
          <div className="form-actions">
            <button
              type="submit"
              disabled={
                !!store.groups.find(
                  (g) => g.id === (choice ?? row?.group_id) && g.is_archived,
                )
              }
            >
              {store.busy ? "Saving…" : "Save trip assignment"}
            </button>
            <button type="button" onClick={onClose}>
              Cancel
            </button>
          </div>
        </fieldset>
        {store.error && (
          <button type="button" onClick={store.reload}>
            Reload trip groups
          </button>
        )}
      </form>
    </aside>
  );
}
