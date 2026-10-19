import { z } from "zod";
import type { BrowserClient } from "./client";
import { entrySchema, type Entry } from "./domain";

export const sourceSchema = z.object({
  id: z.string(),
  statement_id: z.string(),
  card_label: z.string(),
  bank: z.string(),
  statement_date: z.string().nullable(),
  parsed_statement_date: z.string().nullable(),
  source_filename: z.string(),
  parser_version: z.string(),
  extractor_version: z.string(),
  page_count: z.number().int().positive(),
  entry_count: z.number().int().nonnegative(),
  state: z.enum(["selected", "candidate", "superseded", "rejected"]),
  source_import_id: z.string().nullable(),
  issues: z.array(z.object({ code: z.string() }).passthrough()),
});
export type Source = z.infer<typeof sourceSchema>;
export const revisionSchema = z.object({
  id: z.string(),
  base_import_id: z.string().nullable(),
  candidate_import_id: z.string(),
  status: z.enum(["pending", "accepted", "rejected"]),
  plan: z.object({
    matches: z.array(
      z.object({ new_entry_id: z.string(), previous_entry_id: z.string() }),
    ),
    unmatched_new: z.array(z.string()),
    unmatched_old: z.array(z.string()),
    metadata_changed: z.boolean(),
  }),
});
export type Revision = z.infer<typeof revisionSchema>;
export type IdentityMapping = {
  new_entry_id: string;
  previous_entry_id: string | null;
};

export async function readSources(api: BrowserClient, signal: AbortSignal) {
  const rows: Source[] = [];
  for (let offset = 0; ; offset += 100) {
    const { data, error } = await api
      .from("sources")
      .select("*")
      .order("created_at", { ascending: false })
      .order("id")
      .range(offset, offset + 99)
      .abortSignal(signal);
    if (error)
      throw Error(
        "Could not load imports. The reviewed database upgrade and an available connection are required.",
      );
    const page = z.array(sourceSchema).parse(data);
    rows.push(...page);
    if (page.length < 100) return rows;
  }
}
export async function readRevisionEntries(
  api: BrowserClient,
  imports: string[],
  signal: AbortSignal,
) {
  const rows: Entry[] = [];
  for (let offset = 0; ; offset += 100) {
    const { data, error } = await api
      .from("revision_entries")
      .select("*")
      .in("import_id", imports)
      .order("sequence")
      .order("id")
      .range(offset, offset + 99)
      .abortSignal(signal);
    if (error) throw Error("Could not load source entries.");
    const page = z.array(entrySchema).parse(data);
    rows.push(...page);
    if (page.length < 100) return rows;
  }
}
export function demoSources(rows: Entry[]): Source[] {
  const groups = new Map<string, Entry[]>();
  for (const row of rows)
    groups.set(row.import_id, [...(groups.get(row.import_id) ?? []), row]);
  return [...groups].map(([id, entries]) => {
    const row = entries[0];
    return {
      id,
      statement_id: row.statement_id,
      card_label: row.card_label,
      bank: row.bank,
      statement_date: row.statement_date,
      parsed_statement_date: row.statement_date,
      source_filename: "synthetic-statement.pdf",
      parser_version: "synthetic-1",
      extractor_version: "synthetic-1",
      page_count: 1,
      entry_count: entries.length,
      state: row.source_state ?? (row.is_selected ? "selected" : "candidate"),
      source_import_id: null,
      issues: row.import_issues,
    };
  });
}
