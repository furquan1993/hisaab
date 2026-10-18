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
  bank: z.string(),
  statement_date: date,
  transaction_date: date,
  description: z.string(),
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
});
export type Entry = z.infer<typeof entrySchema>;
export type View = "statement" | "transaction" | "review";

export function filterEntries(
  rows: Entry[],
  view: View,
  start: string,
  end: string,
) {
  return rows.filter((row) => {
    if (view === "review") return row.needs_review;
    const date =
      view === "statement" ? row.statement_date : row.transaction_date;
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
