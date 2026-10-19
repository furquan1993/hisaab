import { useRef, useState, type FormEvent } from "react";
import { banks, type Card, type CardDraft } from "./useCards";

export default function Cards({
  cards,
  loading,
  error,
  onSave,
  onReload,
  onBusyChange,
}: {
  cards: Card[];
  loading: boolean;
  error: string;
  onSave: (draft: CardDraft) => Promise<Card>;
  onReload: () => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const [editing, setEditing] = useState<Card | null>(null);
  const [label, setLabel] = useState("");
  const [bank, setBank] = useState<Card["bank"]>("hdfc");
  const [digits, setDigits] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [notice, setNotice] = useState("");
  const nameInput = useRef<HTMLInputElement>(null);
  function reset() {
    setEditing(null);
    setLabel("");
    setBank("hdfc");
    setDigits("");
    setFailure("");
    nameInput.current?.focus();
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    setFailure("");
    setNotice("");
    if (
      !label.trim() ||
      label.trim().length > 120 ||
      (digits && !/^[0-9]{4}$/.test(digits))
    ) {
      setFailure(
        "Use a card name of 1 to 120 characters and, optionally, exactly four digits.",
      );
      return;
    }
    setBusy(true);
    onBusyChange(true);
    try {
      await onSave({
        id: editing?.id ?? null,
        version: editing?.version ?? 0,
        label: label.trim(),
        bank,
        last_four: digits || null,
      });
      reset();
      setNotice(
        editing
          ? "Card updated."
          : "Card added. You can now import statements for it.",
      );
    } catch (error) {
      setFailure(
        error instanceof Error ? error.message : "Could not confirm the save.",
      );
    } finally {
      setBusy(false);
      onBusyChange(false);
    }
  }
  return (
    <section className="page label-page">
      <span className="eyebrow">YOUR CREDIT CARDS</span>
      <h1>Cards</h1>
      <p>
        Add a credit card before importing its statements, or edit its name and
        last four digits here.
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
      <div className="ledger label-manager card-manager">
        <form onSubmit={submit}>
          <h2>{editing ? "Edit card" : "Add card"}</h2>
          <fieldset disabled={busy || loading || !!error}>
            <label>
              Card name
              <input
                ref={nameInput}
                value={label}
                maxLength={120}
                required
                placeholder="e.g. HDFC Regalia"
                onChange={(event) => setLabel(event.target.value)}
              />
            </label>
            <div>
              <label htmlFor="card-bank">Bank</label>
              <select
                id="card-bank"
                value={bank}
                disabled={editing?.has_statements}
                onChange={(event) =>
                  setBank(event.target.value as Card["bank"])
                }
              >
                {Object.entries(banks).map(([value, name]) => (
                  <option key={value} value={value}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
            {editing?.has_statements && (
              <p>Bank is fixed because this card already has statements.</p>
            )}
            <label>
              Last four digits (optional)
              <input
                value={digits}
                inputMode="numeric"
                pattern="[0-9]{4}"
                maxLength={4}
                placeholder="1234"
                onChange={(event) => setDigits(event.target.value)}
              />
            </label>
            <div className="form-actions">
              <button type="submit">
                {busy ? "Saving…" : editing ? "Save changes" : "Add card"}
              </button>
              {editing && (
                <button type="button" className="quiet" onClick={reset}>
                  Cancel
                </button>
              )}
            </div>
          </fieldset>
        </form>
        <div className="ledger-heading">
          <h2>Saved cards</h2>
          <button type="button" disabled={busy || loading} onClick={onReload}>
            Reload cards
          </button>
        </div>
        {loading && <p role="status">Loading cards…</p>}
        {!loading && !error && !cards.length && (
          <p className="empty">No cards yet. Add your first card above.</p>
        )}
        <ul className="label-list">
          {[...cards]
            .sort((a, b) => a.label.localeCompare(b.label))
            .map((card) => (
              <li key={card.id}>
                <div>
                  <strong>{card.label}</strong>
                  <small>
                    {banks[card.bank]}
                    {card.last_four ? ` · •••• ${card.last_four}` : ""}
                  </small>
                  <small>Card ID: {card.id}</small>
                </div>
                <button
                  type="button"
                  disabled={busy || loading || !!error}
                  aria-label={`Edit ${card.label}`}
                  onClick={() => {
                    setEditing(card);
                    setLabel(card.label);
                    setBank(card.bank);
                    setDigits(card.last_four ?? "");
                    setFailure("");
                    setNotice("");
                    nameInput.current?.focus();
                  }}
                >
                  Edit
                </button>
              </li>
            ))}
        </ul>
      </div>
    </section>
  );
}
