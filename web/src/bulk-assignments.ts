import { z } from "zod";
import type { BrowserClient } from "./client";
import type { Entry } from "./domain";

const savedDecision = z.object({
  account_id: z.string().nullable(),
  category_id: z.string().nullable(),
  version: z.number().int().nonnegative(),
});

// Reuse guarded individual saves. Stop at the first unconfirmed write.
export async function saveBulkAssignments(
  api: BrowserClient | null,
  rows: Entry[],
  kind: "account" | "category",
  value: string | null,
) {
  if (!rows.length || rows.length > 50)
    throw Error("Choose 1 to 50 transactions on this page.");
  const saved: Entry[] = [];
  let error = "";
  for (const row of rows) {
    try {
      if (!row.is_selected)
        throw Error("Only selected-source entries can be updated.");
      if (api) {
        const result = await api.rpc("save_entry_decision", {
          p_entry_id: row.id,
          p_expected_version: row.decision_version,
          p_patch: { [`${kind}_id`]: value },
        });
        if (result.error)
          throw Error(
            result.error.code === "PT409"
              ? "A transaction changed elsewhere. Refresh and review it before retrying."
              : "A save could not be confirmed. Refresh before retrying.",
          );
        const parsed = savedDecision.safeParse(result.data);
        if (!parsed.success)
          throw Error("A save could not be verified. Refresh before retrying.");
        const decision = parsed.data;
        saved.push({
          ...row,
          account_id: decision.account_id,
          category_id: decision.category_id,
          decision_version: decision.version,
        });
      } else {
        saved.push({
          ...row,
          [`${kind}_id`]: value,
          decision_version: row.decision_version + 1,
        });
      }
    } catch (e) {
      error =
        e instanceof Error
          ? e.message
          : "A save could not be confirmed. Refresh before retrying.";
      break;
    }
  }
  return { saved, error };
}
