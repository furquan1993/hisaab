import { useEffect, useState } from "react";
import { z } from "zod";
import type { BrowserClient } from "./client";
import { demoEntries } from "./demo";

export const banks = { hdfc: "HDFC Bank", sbi: "SBI", yes_bank: "YES Bank" };
export const cardSchema = z.object({
  id: z.string(),
  label: z.string().trim().min(1).max(120),
  bank: z.enum(["hdfc", "sbi", "yes_bank"]),
  last_four: z
    .string()
    .regex(/^[0-9]{4}$/)
    .nullable(),
  version: z.number().int().positive(),
  has_statements: z.boolean(),
});
export type Card = z.infer<typeof cardSchema>;
export type CardDraft = Omit<Card, "id" | "has_statements"> & {
  id: string | null;
};

export function useCards(
  api: BrowserClient | null,
  ownerId?: string,
  active = true,
) {
  const [cards, setCards] = useState<Card[]>(() =>
    api
      ? []
      : [
          ...new Map(
            demoEntries.map((row) => [
              row.card_id,
              cardSchema.parse({
                id: row.card_id,
                label: row.card_label,
                bank: row.bank,
                last_four: null,
                version: 1,
                has_statements: true,
              }),
            ]),
          ).values(),
        ],
  );
  const [loading, setLoading] = useState(!!api);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!api || !active) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    (async () => {
      const all: Card[] = [];
      for (let offset = 0; ; offset += 100) {
        const { data, error } = await api
          .from("cards")
          .select("*")
          .order("label")
          .order("id")
          .range(offset, offset + 99)
          .abortSignal(controller.signal);
        if (error) throw error;
        const page = z.array(cardSchema).parse(data);
        all.push(...page);
        if (page.length < 100) break;
      }
      if (!controller.signal.aborted) setCards(all);
    })()
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            "Could not load cards. Check your connection and that card management is enabled, then reload.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, active, refresh]);

  async function save(draft: CardDraft) {
    let saved: Card;
    if (api) {
      if (!ownerId)
        throw Error("Reload your signed-in workspace before saving.");
      const { data, error } = await api.rpc("save_card", {
        p_expected_owner: ownerId,
        p_id: draft.id,
        p_expected_version: draft.id ? draft.version : 0,
        p_label: draft.label.trim(),
        p_bank: draft.bank,
        p_last_four: draft.last_four,
      });
      if (error)
        throw Error(
          error.code === "PT409"
            ? "This card changed or its bank can no longer be changed. Your draft is kept; cancel and reload cards before retrying."
            : "Could not confirm the save. Your draft is kept; reload cards before retrying.",
        );
      saved = cardSchema.parse(data);
    } else {
      const previous = cards.find((card) => card.id === draft.id);
      saved = cardSchema.parse({
        ...draft,
        label: draft.label.trim(),
        id: draft.id ?? crypto.randomUUID(),
        version: (previous?.version ?? 0) + 1,
        has_statements: previous?.has_statements ?? false,
      });
    }
    setCards((current) => [
      ...current.filter((card) => card.id !== saved.id),
      saved,
    ]);
    return saved;
  }
  return {
    cards,
    loading,
    error,
    save,
    reload: () => setRefresh((n) => n + 1),
  };
}
