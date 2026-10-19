import { useEffect, useState } from "react";
import { z } from "zod";
import type { BrowserClient } from "./client";
import { formatAmount, type Entry } from "./domain";
import { reviewedValues } from "./review-domain";
import type { FundingGroup } from "./funding-domain";
const rowSchema = z.object({
  id: z.string(),
  effective_description: z.string(),
  effective_amount: z
    .string()
    .regex(/^\d+\.\d{2}$/)
    .nullable(),
  effective_direction: z.enum(["debit", "credit"]).nullable(),
  effective_entry_type: z.string(),
  effective_transaction_date: z.string().nullable(),
});
type Row = z.infer<typeof rowSchema>;
export default function FundingEntries({
  api,
  group,
  demoRows,
}: {
  api: BrowserClient | null;
  group: FundingGroup;
  demoRows: Entry[];
}) {
  const [open, setOpen] = useState(false),
    [offset, setOffset] = useState(0),
    [rows, setRows] = useState<Row[]>([]),
    [total, setTotal] = useState(0),
    [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setRows([]);
    (async () => {
      if (api) {
        let query = api
          .from("funding_entries")
          .select("*", { count: "exact" })
          .eq("card_id", group.card_id);
        for (const key of ["account_id", "currency", "month"] as const)
          query =
            group[key] === null
              ? query.is(key, null)
              : query.eq(key, group[key]);
        const { data, error, count } = await query
          .order("id")
          .range(offset, offset + 49)
          .abortSignal(controller.signal);
        if (error) throw Error();
        if (!controller.signal.aborted) {
          setRows(z.array(rowSchema).parse(data));
          setTotal(count ?? 0);
        }
      } else {
        const all = demoRows
          .filter((r) => {
            const v = reviewedValues(r),
              date =
                r.effective_statement_date === undefined
                  ? r.statement_date
                  : r.effective_statement_date;
            return (
              r.is_selected &&
              v.entry_type !== "payment" &&
              (r.card_id ?? r.card_label) === group.card_id &&
              r.account_id === group.account_id &&
              v.currency === group.currency &&
              (date ? date.slice(0, 7) + "-01" : null) === group.month
            );
          })
          .map((r) => {
            const v = reviewedValues(r);
            return {
              id: r.id,
              effective_description: v.description,
              effective_amount: v.amount,
              effective_direction: v.direction,
              effective_entry_type: v.entry_type,
              effective_transaction_date: v.transaction_date,
            };
          });
        setRows(all.slice(offset, offset + 50));
        setTotal(all.length);
      }
    })()
      .catch(() => {
        if (!controller.signal.aborted)
          setError("Could not load included entries.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, open, offset, group, demoRows]);
  return (
    <details
      className="funding-entries"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>
        Included entries · {group.month?.slice(0, 7) ?? "Month unknown"}
      </summary>
      {open && (
        <>
          {loading && <p role="status">Loading included entries…</p>}
          {error && <p role="alert">{error}</p>}
          <ul>
            {rows.map((r) => (
              <li key={r.id}>
                {r.effective_description} ·{" "}
                {r.effective_transaction_date ?? "Date unknown"} ·{" "}
                {r.effective_entry_type} ·{" "}
                {formatAmount(
                  r.effective_amount,
                  group.currency,
                  r.effective_direction,
                )}
              </li>
            ))}
          </ul>
          <div className="form-actions">
            <span>
              {total ? offset + 1 : 0}–{Math.min(offset + rows.length, total)}{" "}
              of {total}
            </span>
            <button
              type="button"
              disabled={loading || !offset}
              onClick={() => setOffset((n) => n - 50)}
            >
              Previous entries
            </button>
            <button
              type="button"
              disabled={loading || offset + 50 >= total}
              onClick={() => setOffset((n) => n + 50)}
            >
              Next entries
            </button>
          </div>
        </>
      )}
    </details>
  );
}
