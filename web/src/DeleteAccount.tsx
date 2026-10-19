import { useEffect, useRef, useState } from "react";
import type { AccountDeletion } from "./account-deletion";

export default function DeleteAccount({
  preview,
  onConfirm,
  onClose,
}: {
  preview: AccountDeletion;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}) {
  const cancel = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    dialog.current?.showModal();
    cancel.current?.focus();
  }, []);
  function close() {
    dialog.current?.close();
    onClose();
  }
  async function confirm() {
    setBusy(true);
    setError("");
    try {
      await onConfirm();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not confirm deletion.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog
      ref={dialog}
      className="delete-account-dialog"
      aria-labelledby="delete-account-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) close();
      }}
    >
      <h2 id="delete-account-title">Delete {preview.account.name}?</h2>
      <p>
        This permanently removes the account. The {preview.entries.length}{" "}
        {preview.entries.length === 1 ? "transaction" : "transactions"} below
        will become unassigned. Their categories and other details will be kept.
      </p>
      <p>
        All dates and statement sources are included. Previous reconciliation
        receipts and decision history are retained.
      </p>
      {preview.entries.length === 0 ? (
        <p>No transactions are assigned to this account.</p>
      ) : (
        <div
          className="delete-account-transactions"
          tabIndex={0}
          aria-label="Affected transactions"
        >
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Transaction</th>
                <th>Card</th>
                <th>Amount</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {preview.entries.map((entry) => (
                <tr key={entry.id}>
                  <td data-label="Date">
                    {entry.effective_transaction_date ??
                      entry.transaction_date ??
                      "Unknown date"}
                  </td>
                  <td data-label="Transaction">
                    {entry.friendly_description ??
                      entry.effective_description ??
                      entry.description}
                  </td>
                  <td data-label="Card">{entry.card_label}</td>
                  <td data-label="Amount">
                    {entry.effective_currency ?? entry.currency}{" "}
                    {entry.effective_amount ?? entry.amount ?? "Unknown amount"}{" "}
                    ({entry.effective_direction ?? entry.direction ?? "unknown"}
                    )
                  </td>
                  <td data-label="Source">
                    {entry.is_selected ? "Selected" : "Historical / candidate"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="form-actions">
        <button ref={cancel} type="button" disabled={busy} onClick={close}>
          Cancel
        </button>
        <button
          type="button"
          className="danger"
          disabled={busy || !!error}
          onClick={() => void confirm()}
        >
          {busy ? "Deleting…" : "Delete account and unassign transactions"}
        </button>
      </div>
    </dialog>
  );
}
