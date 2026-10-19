import { readPage, type BrowserClient } from "./client";
import { monthRange, type Entry } from "./domain";
import { readStatementBills } from "./statement-bills";

export type SummaryBasis = "statement" | "transaction";

export async function readSummary(
  api: BrowserClient,
  month: string,
  basis: SummaryBasis,
  signal: AbortSignal,
) {
  const [start, end] = monthRange(month + "-01");
  const readEntries = async () => {
    const rows: Entry[] = [];
    const ids = new Set<string>();
    for (;;) {
      if (signal.aborted) throw new Error("Summary loading cancelled.");
      const page = await readPage(
        api,
        basis,
        start,
        end,
        rows.length,
        signal,
        "reviewed",
      );
      for (const row of page.rows) {
        if (ids.has(row.id))
          throw new Error("Entries changed while loading. Reload the summary.");
        ids.add(row.id);
        rows.push(row);
      }
      if (rows.length >= page.total) return rows;
      if (!page.rows.length)
        throw new Error("Entries changed while loading. Reload the summary.");
    }
  };
  const readUndated = async () => {
    const { error, count } = await api
      .from("entries")
      .select("id", { count: "exact", head: true })
      .eq("is_selected", true)
      .is(`effective_${basis}_date`, null)
      .abortSignal(signal);
    if (error || count === null)
      throw new Error(
        "Could not check entries with unknown dates. Reload the summary.",
      );
    return count;
  };
  const [rows, undated, billResult] = await Promise.all([
    readEntries(),
    readUndated(),
    basis === "statement"
      ? readStatementBills(api, start, end, signal)
          .then((bills) => ({ bills, billsError: "" }))
          .catch(() => ({
            bills: [],
            billsError:
              "Printed bill balances could not be loaded. Reload to retry. Spending is shown separately below.",
          }))
      : Promise.resolve({ bills: [], billsError: "" }),
  ]);
  return { rows, undated, ...billResult };
}
