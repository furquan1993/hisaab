import { z } from "zod";
import type { BrowserClient } from "./client";
import { entrySchema } from "./domain";
import type { SpendingEntry, SpendingGroup } from "./spending-domain";

export const spendingGroupSchema = z.object({
  id: z.string().uuid(),
  name: z.string().min(1).max(120),
  is_archived: z.boolean(),
  version: z.number().int().positive(),
});
export const spendingEntrySchema = entrySchema.extend({
  group_id: z.string().uuid().nullable(),
  group_name: z.string().nullable(),
  group_version: z.number().int().nonnegative(),
});
export const spendingAssignmentSchema = z.object({
  entry_id: z.string(),
  group_id: z.string().nullable(),
  version: z.number().int().nonnegative(),
});
export type SpendingAssignment = z.infer<typeof spendingAssignmentSchema>;

// Inclusive ranges and stable ordering: https://supabase.com/docs/reference/javascript/range
export async function readSpending(api: BrowserClient, signal: AbortSignal) {
  async function pages<T extends { id: string }>(
    table: string,
    schema: z.ZodType<T>,
  ) {
    const all: T[] = [],
      ids = new Set<string>();
    let expected: number | null = null;
    for (;;) {
      if (signal.aborted) throw Error("Spending loading cancelled.");
      const { data, error, count } = await api
        .from(table)
        .select("*", { count: "exact" })
        .order("id")
        .range(all.length, all.length + 99)
        .abortSignal(signal);
      if (error || count === null)
        throw Error(
          "Could not load spending. Check your connection and database upgrade, then reload.",
        );
      if (expected !== null && expected !== count)
        throw Error(
          "Spending changed while loading. Reload before continuing.",
        );
      expected = count;
      const parsed = z.array(schema).safeParse(data);
      if (!parsed.success)
        throw Error("Could not read spending data. Reload before continuing.");
      const batch = parsed.data;
      for (const row of batch) {
        if (ids.has(row.id))
          throw Error(
            "Spending changed while loading. Reload before continuing.",
          );
        ids.add(row.id);
        all.push(row);
      }
      if (all.length === count) return all;
      if (!batch.length || all.length > count)
        throw Error(
          "Spending changed while loading. Reload before continuing.",
        );
    }
  }
  const [rows, groups] = await Promise.all([
    pages<SpendingEntry>("spending_entries", spendingEntrySchema),
    pages<SpendingGroup>("spending_groups", spendingGroupSchema),
  ]);
  return { rows, groups };
}

export async function assignSpendingGroup(
  api: BrowserClient,
  ownerId: string,
  groupId: string | null,
  rows: SpendingEntry[],
) {
  const { data, error } = await api.rpc("assign_spending_group", {
    p_group_id: groupId,
    p_entries: rows.map((row) => ({ id: row.id, version: row.group_version })),
    p_expected_owner: ownerId,
  });
  if (error)
    throw Error(
      error.code === "PT409"
        ? "A transaction or group assignment changed. Reload spending before retrying; this batch was not saved."
        : "Could not confirm group assignments. Reload spending before retrying.",
    );
  const parsed = z.array(spendingAssignmentSchema).safeParse(data);
  if (!parsed.success)
    throw Error(
      "Could not verify saved assignments. Reload spending before continuing.",
    );
  const saved = parsed.data;
  const roots = new Set(rows.map((row) => row.logical_entry_id ?? row.id));
  if (
    saved.length !== roots.size ||
    new Set(saved.map((s) => s.entry_id)).size !== roots.size ||
    saved.some((s) => !roots.has(s.entry_id) || s.group_id !== groupId)
  )
    throw Error(
      "Could not verify saved assignments. Reload spending before continuing.",
    );
  return saved;
}
