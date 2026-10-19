import { z } from "zod";
import type { BrowserClient } from "./client";
import type { Entry } from "./domain";

export async function assignEntries(
  api: BrowserClient,
  ownerId: string,
  rows: Entry[],
  signal: AbortSignal,
) {
  const ids = rows
    .filter((row) => row.is_selected && (!row.account_id || !row.category_id))
    .map((row) => row.id);
  if (!ids.length) return 0;
  const { data, error } = await api
    .rpc("auto_assign_entries", {
      p_entry_ids: ids,
      p_expected_owner: ownerId,
    })
    .abortSignal(signal);
  if (error)
    throw new Error(
      "Automatic assignments are unavailable. Retry after checking the connection and database upgrade.",
    );
  return z.number().int().min(0).max(ids.length).parse(data);
}
