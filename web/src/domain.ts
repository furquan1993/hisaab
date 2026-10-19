import { z } from "zod";

const date = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/)
  .nullable();
export const entrySchema = z.object({
  id: z.string(),
  import_id: z.string(),
  statement_id: z.string(),
  card_label: z.string(),
  card_id: z.string().optional(),
  bank: z.string(),
  statement_date: date,
  transaction_date: date,
  description: z.string(),
  friendly_description: z.string().nullable().default(null),
  friendly_description_version: z.number().int().nonnegative().default(0),
  amount: z
    .string()
    .regex(/^\d+\.\d{2}$/)
    .nullable(),
  direction: z.enum(["debit", "credit"]).nullable(),
  currency: z.string().nullable(),
  entry_type: z.string(),
  sequence: z.number().int().positive(),
  is_selected: z.boolean(),
  needs_review: z.boolean(),
  entry_issues: z.array(z.object({ code: z.string() }).passthrough()),
  import_issues: z.array(z.object({ code: z.string() }).passthrough()),
  review_status: z.string(),
  source_state: z
    .enum(["selected", "candidate", "superseded", "rejected"])
    .optional(),
  logical_entry_id: z.string().optional(),
  decision_version: z.number().int().nonnegative().default(0),
  category_id: z.string().nullable().default(null),
  category_name: z.string().nullable().default(null),
  account_id: z.string().nullable().default(null),
  account_name: z.string().nullable().default(null),
  overrides: z.record(z.string(), z.string()).default({}),
  applied_overrides: z.record(z.string(), z.string()).default({}),
  applied_acknowledged: z.array(z.string()).default([]),
  review_stale: z.boolean().default(false),
  effective_transaction_date: date.optional(),
  original_transaction_time: z.string().nullable().optional(),
  effective_transaction_time: z.string().nullable().optional(),
  effective_statement_date: date.optional(),
  printed_statement_date: date.optional(),
  effective_description: z.string().optional(),
  effective_amount: z
    .string()
    .regex(/^\d+\.\d{2}$/)
    .nullable()
    .optional(),
  effective_direction: z.enum(["debit", "credit"]).nullable().optional(),
  effective_currency: z.string().nullable().optional(),
  effective_entry_type: z.string().optional(),
  unresolved_entry_issues: z
    .array(z.object({ code: z.string() }).passthrough())
    .optional(),
  unresolved_import_issues: z
    .array(z.object({ code: z.string() }).passthrough())
    .optional(),
  import_review_version: z.number().int().nonnegative().default(0),
  import_acknowledged: z.array(z.string()).default([]),
  import_review_stale: z.boolean().default(false),
  statement_date_override: date.optional(),
  decision_reason: z.string().nullable().optional(),
  demo_review_signature: z.string().optional(),
});
export type Entry = z.infer<typeof entrySchema>;
export type View = "statement" | "transaction" | "review";
export type DateBasis = "original" | "reviewed";
export type DateSort = "newest" | "oldest";

export function sortEntries(rows: Entry[], order: DateSort) {
  return [...rows].sort((a, b) => {
    const first =
      a.effective_transaction_date === undefined
        ? a.transaction_date
        : a.effective_transaction_date;
    const second =
      b.effective_transaction_date === undefined
        ? b.transaction_date
        : b.effective_transaction_date;
    if (first === null && second !== null) return 1;
    if (second === null && first !== null) return -1;
    const dateOrder =
      (first ?? "").localeCompare(second ?? "") * (order === "oldest" ? 1 : -1);
    return (
      dateOrder ||
      a.import_id.localeCompare(b.import_id) ||
      a.sequence - b.sequence ||
      a.id.localeCompare(b.id)
    );
  });
}

export function filterEntries(
  rows: Entry[],
  view: View,
  start: string,
  end: string,
  basis: DateBasis = "original",
) {
  return rows.filter((row) => {
    if (view === "review") return row.needs_review;
    const original =
      view === "statement" ? row.statement_date : row.transaction_date;
    const effective =
      view === "statement"
        ? row.effective_statement_date
        : row.effective_transaction_date;
    const date =
      basis === "reviewed" && effective !== undefined ? effective : original;
    return row.is_selected && date !== null && date >= start && date <= end;
  });
}

export function formatAmount(
  amount: string | null,
  currency: string | null,
  direction: Entry["direction"],
) {
  if (amount === null) return "Amount unknown";
  const [whole, fraction] = amount.split(".");
  // Intl formats BigInt without a lossy Number conversion.
  // https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/format
  const grouped = new Intl.NumberFormat("en-IN").format(BigInt(whole));
  const sign =
    direction === "credit" ? "+ " : direction === "debit" ? "− " : "";
  return `${sign}${currency ?? "?"} ${grouped}.${fraction}`;
}

export function monthRange(date: string) {
  const [year, month] = date.slice(0, 7).split("-").map(Number);
  return [
    `${year}-${String(month).padStart(2, "0")}-01`,
    `${year}-${String(month).padStart(2, "0")}-${new Date(year, month, 0).getDate()}`,
  ] as const;
}
