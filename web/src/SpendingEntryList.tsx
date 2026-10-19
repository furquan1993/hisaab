import { formatAmount } from "./domain";
import { reviewedValues } from "./review-domain";
import type { SpendingEntry } from "./spending-domain";
import type { Label } from "./useLabels";

export function spendingDate(date: string | null) {
  if (!date) return "Date unknown";
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(date + "T00:00:00Z"));
}
export default function SpendingEntryList({
  rows,
  labels,
  selection,
  onSelect,
  disabled = false,
}: {
  rows: SpendingEntry[];
  labels: Label[];
  selection?: Set<string>;
  onSelect?: (row: SpendingEntry, checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <ul className="spending-entry-list" aria-label="Spending transactions">
      {rows.map((row) => {
        const values = reviewedValues(row);
        const category =
          labels.find((l) => l.id === row.category_id && l.kind === "category")
            ?.name ??
          row.category_name ??
          "Uncategorized";
        const account =
          labels.find((l) => l.id === row.account_id && l.kind === "account")
            ?.name ??
          row.account_name ??
          "Unassigned account";
        const description = row.friendly_description ?? values.description;
        return (
          <li key={row.id}>
            {onSelect && (
              <input
                type="checkbox"
                aria-label={`Select ${description}`}
                checked={selection?.has(row.id) ?? false}
                disabled={
                  disabled ||
                  ((selection?.size ?? 0) >= 50 && !selection?.has(row.id))
                }
                onChange={(e) => onSelect(row, e.target.checked)}
              />
            )}
            <div className="spending-entry-info">
              <strong>{description}</strong>
              <div className="spending-entry-meta">
                <time dateTime={values.transaction_date ?? undefined}>
                  {spendingDate(values.transaction_date)}
                </time>
                <span>{category}</span>
                <span>
                  {row.card_label} · {account}
                </span>
                {onSelect && <span>{row.group_name ?? "Ungrouped"}</span>}
                {row.needs_review && (
                  <span className="spending-review">Needs review</span>
                )}
              </div>
            </div>
            <span
              className={`spending-entry-amount ${values.direction ?? "unknown"}`}
            >
              {formatAmount(values.amount, values.currency, values.direction)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
