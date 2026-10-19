import { createClient } from "@supabase/supabase-js";
import { z } from "zod";
import {
  entrySchema,
  type View,
  type DateBasis,
  type DateSort,
} from "./domain";

import { validatePublicConfig } from "./public-config";
export { validatePublicConfig } from "./public-config";
const url = import.meta.env.VITE_SUPABASE_URL ?? "";
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? "";
export const storageKey = `hisaab.auth.${validatePublicConfig(url, key) ? new URL(url).hostname : "unconfigured"}`;
// A tab-scoped session survives reload without caching financial rows.
// https://supabase.com/docs/reference/javascript/initializing
export const client = validatePublicConfig(url, key)
  ? createClient(url, key, {
      db: { schema: "hisaab_api" },
      auth: {
        storage: window.sessionStorage,
        storageKey,
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: false,
      },
    })
  : null;

export type BrowserClient = NonNullable<typeof client>;

export async function readPage(
  api: BrowserClient,
  view: View,
  start: string,
  end: string,
  offset: number,
  signal: AbortSignal,
  basis: DateBasis = "original",
  sort: DateSort = "newest",
) {
  let query = api.from("entries").select("*", { count: "exact" });
  if (view === "review") query = query.eq("needs_review", true);
  else {
    const field =
      (basis === "reviewed" ? "effective_" : "") +
      (view === "statement" ? "statement_date" : "transaction_date");
    query = query.eq("is_selected", true).gte(field, start).lte(field, end);
  }
  const { data, error, count } = await query
    .order("effective_transaction_date", {
      ascending: sort === "oldest",
      nullsFirst: false,
    })
    .order("import_id")
    .order("sequence")
    .order("id")
    .range(offset, offset + 49)
    .abortSignal(signal);
  if (error)
    throw new Error(
      "Could not load entries. Check your connection and API setup.",
    );
  return { rows: z.array(entrySchema).parse(data), total: count ?? 0 };
}

export const evidenceSchema = z
  .object({
    id: z.string(),
    import_id: z.string(),
    source_raw_text: z.string(),
    source_page: z.number(),
    raw_date: z.string(),
    raw_amount: z.string(),
    source_filename: z.string(),
    parser_version: z.string(),
    file_sha256: z.string(),
    pdf_deleted_at: z.string().nullable(),
  })
  .passthrough();

export async function downloadOriginal(api: BrowserClient, importId: string) {
  const { data, error } = await api.rpc("original_pdf", {
    p_import_id: importId,
  });
  if (error || !data)
    throw new Error("Original unavailable or integrity check failed.");
  const payload = z
    .object({
      sha256: z.string().regex(/^[a-f0-9]{64}$/),
      content_base64: z.string(),
    })
    .parse(data);
  const bytes = Uint8Array.from(atob(payload.content_base64), (c) =>
    c.charCodeAt(0),
  );
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const hex = [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  if (hex !== payload.sha256)
    throw new Error("Original integrity check failed.");
  const link = document.createElement("a");
  link.href = URL.createObjectURL(
    new Blob([bytes], { type: "application/pdf" }),
  );
  link.download = "statement.pdf";
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
