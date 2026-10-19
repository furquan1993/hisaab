import { useEffect, useState } from "react";
import { z } from "zod";
import type { BrowserClient } from "./client";
import type { Source } from "./revisions-client";

const cardSchema = z.object({
  id: z.string().uuid(),
  label: z.string(),
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
          .from("cards")
          .select("id,label")
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
  const selectedCard = cards.find((card) => card.id === cardId) ?? cards[0];
  const selectedSource =
    sources.find((source) => source.id === importId) ?? sources[0];
  return (
    <div className="import-commands">
      <details>
        <summary>First time? Set up the local importer</summary>
        <p>
          Importing needs Git, uv, repository access, and the same email and
          password you use to sign in here. The CLI signs in separately and
          keeps its session in memory. No database password is needed.
        </p>
        <ol>
          <li>
            Install Git and uv, then run these once in your terminal:
            <pre>
              <code>{`git clone https://github.com/furquan1993/hisaab.git
cd hisaab
uv sync --locked`}</code>
            </pre>
            Already cloned? Use that folder. uv sets up Python; no local UI,
            Node.js, or manual virtual-environment activation is needed.
          </li>
          <li>
            The public project URL and publishable key are included in
            <code> supabase.public.json</code>, shared with this UI. You do not
            need to create a private configuration file for imports.
          </li>
          <li>
            Add your card in Cards, copy the PDF into the clone’s
            <code> data/</code> folder, then run the import command below from
            the repository root. Enter your UI email and password when asked. If
            the PDF is encrypted, enter its separate PDF password next.
          </li>
        </ol>
        <p>
          <a
            href="https://github.com/furquan1993/hisaab/blob/main/docs/import-your-first-statement.md"
            target="_blank"
            rel="noreferrer"
          >
            Full setup guide and troubleshooting
          </a>
          . Terminal setup examples use macOS, Linux, or Windows with WSL.
        </p>
      </details>
      {selectedCard ? (
        <section className="import-command" aria-label="Import a PDF">
          <h3>Import a PDF</h3>
          <label>
            Card to import into
            <span className="import-select">
              <select
                value={selectedCard.id}
                onChange={(event) => setCardId(event.target.value)}
              >
                {cards.map((card) => (
                  <option key={card.id} value={card.id}>
                    {card.label}
                  </option>
                ))}
              </select>
            </span>
          </label>
          <p>
            Copy your original PDF into this clone’s <code>data/</code>
            directory (create it if needed). Run the command below from the
            repository root, replacing only the PDF path. Quote paths with
            spaces. Encrypted PDFs prompt for their password in the terminal.
          </p>
          <pre>
            <code>{`uv run python -m core import-pdf --owner ${ownerId} --card ${selectedCard.id} data/statement.pdf`}</code>
          </pre>
          <p>
            After importing, choose Reload imports below and review the saved
            statement or candidate. Passwords and session tokens are not saved.
            Keep your clone for next time; no UI deployment is needed to import
            more PDFs.
          </p>
        </section>
      ) : (
        <p>
          No saved cards yet. Add a card in Cards before importing your first
          statement.
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
          <p>
            Operator-only: run the parser again using the saved original PDF.
            This command still requires private database configuration; the
            email/password import flow above is for new PDF files.
          </p>
          <pre>
            <code>{`uv run python -m core reparse-import --owner ${ownerId} --import-id ${selectedSource.id}`}</code>
          </pre>
        </section>
      )}
    </div>
  );
}
