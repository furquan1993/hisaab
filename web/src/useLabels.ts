import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import type { BrowserClient } from "./client";

export const labelSchema = z.object({
  id: z.string().uuid(),
  kind: z.enum(["category", "account"]),
  name: z.string().min(1).max(120),
  is_archived: z.boolean(),
  version: z.number().int().positive(),
});
export type Label = z.infer<typeof labelSchema>;
export type LabelDraft = Omit<Label, "id"> & { id: string | null };

export function useLabels(api: BrowserClient | null) {
  const [labels, setLabels] = useState<Label[]>([]);
  const [loading, setLoading] = useState(!!api);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    if (!api) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    (async () => {
      const all: Label[] = [];
      for (let offset = 0; ; offset += 100) {
        const { data, error } = await api
          .from("labels")
          .select("*")
          .order("kind")
          .order("name")
          .order("id")
          .range(offset, offset + 99)
          .abortSignal(controller.signal);
        if (error) throw error;
        const page = z.array(labelSchema).parse(data);
        all.push(...page);
        if (page.length < 100) break;
      }
      if (!controller.signal.aborted) setLabels(all);
    })()
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            "Could not load labels. Editing needs the reviewed database upgrade and an available connection.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, refresh]);

  async function save(draft: LabelDraft) {
    let saved: Label;
    if (api) {
      const { data, error } = await api.rpc("save_label", {
        p_kind: draft.kind,
        p_name: draft.name,
        p_id: draft.id,
        p_expected_version: draft.id ? draft.version : 0,
        p_archived: draft.is_archived,
      });
      if (error)
        throw new Error(
          error.code === "PT409"
            ? "This label changed or its name already exists. Reload labels before retrying."
            : "Could not save this label. Your changes have not been confirmed.",
        );
      saved = labelSchema.parse(data);
    } else {
      if (
        labels.some(
          (l) =>
            l.kind === draft.kind &&
            l.id !== draft.id &&
            l.name.toLocaleLowerCase() ===
              draft.name.trim().toLocaleLowerCase(),
        )
      )
        throw new Error("This label name already exists.");
      saved = labelSchema.parse({
        ...draft,
        name: draft.name.trim(),
        id: draft.id ?? crypto.randomUUID(),
        version: draft.id ? draft.version + 1 : 1,
      });
    }
    if (mounted.current)
      setLabels((current) => [
        ...current.filter((l) => l.id !== saved.id),
        saved,
      ]);
    return saved;
  }
  return {
    labels,
    loading,
    error,
    save,
    reload: () => setRefresh((n) => n + 1),
  };
}
