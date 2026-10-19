import { useState, type FormEvent } from "react";
import { sortEntries } from "./domain";
import { reviewedValues } from "./review-domain";
import { spendingRows, type SpendingEntry } from "./spending-domain";
import type { SpendingStore } from "./useSpending";
import type { Label } from "./useLabels";
import SpendingEntryList from "./SpendingEntryList";

export default function SpendingAssignments({
  store,
  labels,
  initialGroup,
  entryIds,
  onClose,
  onSaved,
}: {
  store: SpendingStore;
  labels: Label[];
  initialGroup: string | null;
  entryIds?: string[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [destination, setDestination] = useState(initialGroup ?? "");
  const [source, setSource] = useState(entryIds ? "all" : "ungrouped");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Map<string, SpendingEntry>>(
    new Map(),
  );
  const [error, setError] = useState("");
  const candidates = spendingRows(store.rows).filter((row) => {
    if (entryIds && !entryIds.includes(row.id)) return false;
    if (source === "ungrouped" && row.group_id) return false;
    if (source === "current" && row.group_id !== initialGroup) return false;
    return `${reviewedValues(row).description} ${row.card_label} ${row.group_name ?? ""}`
      .toLocaleLowerCase()
      .includes(search.trim().toLocaleLowerCase());
  });
  const sorted = sortEntries(candidates, "newest") as SpendingEntry[];
  const page = sorted.slice(offset, offset + 50);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await store.assign(destination || null, [...selected.values()]);
      onSaved();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not save group assignments.",
      );
    }
  }
  return (
    <form
      className="spending-assignments"
      aria-label="Assign transactions to a group"
      onSubmit={submit}
    >
      <div className="section-head">
        <div>
          <h2>Assign transactions</h2>
          <p className="muted">
            Select up to 50 entries. Category and account stay independent.
          </p>
        </div>
        <button type="button" disabled={store.busy} onClick={onClose}>
          Close
        </button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <fieldset disabled={store.busy || store.loading || !!store.error}>
        <div className="spending-assignment-controls">
          <label>
            Trip or group
            <select
              aria-label="Destination trip or group"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
            >
              <option value="">Ungrouped · remove assignment</option>
              {store.groups
                .filter((g) => !g.is_archived)
                .map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
            </select>
          </label>
          {!entryIds && (
            <label>
              Show entries
              <select
                value={source}
                onChange={(e) => {
                  setSource(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="ungrouped">Ungrouped</option>
                {initialGroup && <option value="current">In this group</option>}
                <option value="all">All spending</option>
              </select>
            </label>
          )}
          <label>
            Find entries
            <input
              type="search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setOffset(0);
              }}
              placeholder="Description or card"
            />
          </label>
        </div>
        <SpendingEntryList
          rows={page}
          labels={labels}
          selection={new Set(selected.keys())}
          disabled={store.busy}
          onSelect={(row, checked) =>
            setSelected((current) => {
              const next = new Map(current);
              if (checked) next.set(row.id, row);
              else next.delete(row.id);
              return next;
            })
          }
        />
        {!page.length && <p className="empty">No matching entries.</p>}
        {sorted.length > 50 && (
          <div className="form-actions">
            <button
              type="button"
              disabled={!offset}
              onClick={() => setOffset((n) => n - 50)}
            >
              Previous entries
            </button>
            <span>
              {offset + 1}–{Math.min(offset + 50, sorted.length)} of{" "}
              {sorted.length}
            </span>
            <button
              type="button"
              disabled={offset + 50 >= sorted.length}
              onClick={() => setOffset((n) => n + 50)}
            >
              Next entries
            </button>
          </div>
        )}
        <div className="form-actions">
          <button type="submit" disabled={!selected.size}>
            {store.busy
              ? "Saving…"
              : `Save ${selected.size} ${selected.size === 1 ? "assignment" : "assignments"}`}
          </button>
          <span role="status">{selected.size} selected</span>
          {selected.size > 0 && (
            <button type="button" onClick={() => setSelected(new Map())}>
              Clear selection
            </button>
          )}
        </div>
      </fieldset>
    </form>
  );
}
