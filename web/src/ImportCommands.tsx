import { useEffect, useState } from "react";
import { z } from "zod";
import type { BrowserClient } from "./client";
import type { Source } from "./revisions-client";

const cardSchema = z.object({
  card_id: z.string().uuid(),
  card_label: z.string(),
});
type Card = z.infer<typeof cardSchema>;

export default function ImportCommands({
  api,
  ownerId,
  sources,
}: {
  api: BrowserClient | null;
  ownerId?: string;
  sources: Source[];
}) {
  const [cards, setCards] = useState<Card[]>([]);
  const [cardId, setCardId] = useState("");
  const [importId, setImportId] = useState("");
  const [loading, setLoading] = useState(!!api);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!api || !ownerId) return;
    const controller = new AbortController();
    setCards([]);
    setCardId("");
    setLoading(true);
    setError("");
    (async () => {
      const all: Card[] = [];
      for (let offset = 0; ; offset += 100) {
        const { data, error } = await api
          .from("statement_bills")
          .select("card_id,card_label")
          .order("id")
          .range(offset, offset + 99)
          .abortSignal(controller.signal);
        if (error) throw error;
        const page = z.array(cardSchema).parse(data);
        all.push(...page);
        if (page.length < 100) break;
      }
      if (!controller.signal.aborted)
        setCards([
          ...new Map(all.map((card) => [card.card_id, card])).values(),
        ]);
    })()
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            "Could not load cards for import. Check the connection and reload.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, ownerId]);
  if (!api)
    return (
      <p>Sign in to see import commands with your owner and card UUIDs.</p>
    );
  if (!ownerId)
    return <p>Reload your signed-in workspace to load import commands.</p>;
  if (loading) return <p role="status">Loading import commands…</p>;
  if (error) return <p role="alert">{error}</p>;
  const selectedCard =
    cards.find((card) => card.card_id === cardId) ?? cards[0];
  const selectedSource =
    sources.find((source) => source.id === importId) ?? sources[0];
  return (
    <div className="import-commands">
      {selectedCard ? (
        <section className="import-command" aria-label="Import a PDF">
          <h3>Import a PDF</h3>
          <label>
            Card to import into
            <span className="import-select">
              <select
                value={selectedCard.card_id}
                onChange={(event) => setCardId(event.target.value)}
              >
                {cards.map((card) => (
                  <option key={card.card_id} value={card.card_id}>
                    {card.card_label}
                  </option>
                ))}
              </select>
            </span>
          </label>
          <p>
            Replace only the PDF path with a file inside the project’s data
            directory.
          </p>
          <pre>
            <code>{`uv run python -m core import-pdf --owner ${ownerId} --card ${selectedCard.card_id} data/statement.pdf`}</code>
          </pre>
        </section>
      ) : (
        <p>
          No card IDs available from selected statements yet. Use the local
          CLI’s cards-list command to find a registered card for your first
          import.
        </p>
      )}
      {selectedSource && (
        <section className="import-command" aria-label="Reparse a statement">
          <h3>Reparse a statement</h3>
          <label>
            Statement to reparse
            <span className="import-select">
              <select
                value={selectedSource.id}
                onChange={(event) => setImportId(event.target.value)}
              >
                {sources.map((source) => (
                  <option key={source.id} value={source.id}>
                    {source.card_label} · {source.source_filename}
                  </option>
                ))}
              </select>
            </span>
          </label>
          <p>Run the parser again using the saved original PDF.</p>
          <pre>
            <code>{`uv run python -m core reparse-import --owner ${ownerId} --import-id ${selectedSource.id}`}</code>
          </pre>
        </section>
      )}
    </div>
  );
}
