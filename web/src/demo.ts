import { entrySchema } from "./domain";
import cases from "./demo-data.json";

// Explicitly invented fixture data, separate from logic. No private input.
const cards: Record<string, [string, string]> = {
  "1": ["Regalia • demo", "hdfc"],
  "2": ["Swiggy • demo", "hdfc"],
  "3": ["SBI • demo", "sbi"],
  "4": ["YES Bank • demo", "yes_bank"],
};
export const demoEntries = cases.map((row, index) =>
  entrySchema.parse({
    id: row.id,
    import_id: `demo-import-${row.card}-${row.bill}-${row.selected}`,
    statement_id: `demo-statement-${row.card}-${row.bill}`,
    card_label: cards[row.card][0],
    card_id: `demo-card-${row.card}`,
    bank: cards[row.card][1],
    statement_date: row.bill,
    transaction_date: row.date || null,
    description: row.description,
    amount: row.amount,
    direction: row.direction,
    currency: "INR",
    entry_type: row.type,
    sequence: index + 1,
    is_selected: row.selected,
    needs_review: !row.date || !row.selected || row.type === "unknown",
    entry_issues: !row.date
      ? [{ code: "date_missing_or_invalid" }]
      : row.type === "unknown"
        ? [{ code: "entry_type_unknown" }]
        : [],
    import_issues: [],
    review_status: "pending",
  }),
);
