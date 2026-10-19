import { useEffect, useRef, useState } from "react";
import type { BrowserClient } from "./client";
import type { Entry } from "./domain";
import Evidence from "./Evidence";
import RevisionReview, { SourceTable } from "./RevisionReview";
import {
  demoSources,
  readSources,
  readRevisionEntries,
  revisionSchema,
  type IdentityMapping,
  type Revision,
  type Source,
} from "./revisions-client";

export default function Imports({
  api,
  demoRows,
  onDemoDecision,
  onChanged,
}: {
  api: BrowserClient | null;
  demoRows: Entry[];
  onDemoDecision: (
    candidate: string,
    base: string | null,
    mapping: IdentityMapping[] | null,
  ) => void;
  onChanged: () => void;
}) {
  const [sources, setSources] = useState<Source[]>([]),
    [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true),
    [opening, setOpening] = useState(false);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [comparison, setComparison] = useState<{
    revision: Revision;
    entries: Entry[];
  } | null>(null);
  const [inspection, setInspection] = useState<Entry[] | null>(null),
    [evidence, setEvidence] = useState<Entry | null>(null);
  const heading = useRef<HTMLHeadingElement>(null),
    evidenceTrigger = useRef<HTMLButtonElement | null>(null);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    (api
      ? readSources(api, controller.signal)
      : Promise.resolve(demoSources(demoRows))
    )
      .then((rows) => {
        if (!controller.signal.aborted) setSources(rows);
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "Could not load imports.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, demoRows, refresh]);
  async function open(source: Source, compare: boolean) {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setOpening(true);
    setError("");
    setNotice("");
    setEvidence(null);
    setComparison(null);
    setInspection(null);
    try {
      if (compare) {
        let revision: Revision;
        if (api) {
          const { data, error } = await api
            .rpc("prepare_revision", { p_candidate_import_id: source.id })
            .abortSignal(controller.signal);
          if (error)
            throw Error(
              "Could not prepare this comparison. Reload imports and review the current source.",
            );
          revision = revisionSchema.parse(data);
        } else {
          const base =
            demoRows.find(
              (row) =>
                row.statement_id === source.statement_id && row.is_selected,
            )?.import_id ?? null;
          revision = {
            id: "demo-comparison",
            base_import_id: base,
            candidate_import_id: source.id,
            status: "pending",
            plan: {
              matches: [],
              unmatched_new: demoRows
                .filter((row) => row.import_id === source.id)
                .map((row) => row.id),
              unmatched_old: demoRows
                .filter((row) => row.import_id === base)
                .map((row) => row.id),
              metadata_changed: false,
            },
          };
        }
        const ids = [
          revision.candidate_import_id,
          ...(revision.base_import_id ? [revision.base_import_id] : []),
        ];
        const entries = api
          ? await readRevisionEntries(api, ids, controller.signal)
          : demoRows.filter((row) => ids.includes(row.import_id));
        if (!controller.signal.aborted) setComparison({ revision, entries });
      } else {
        const entries = api
          ? await readRevisionEntries(api, [source.id], controller.signal)
          : demoRows.filter((row) => row.import_id === source.id);
        if (!controller.signal.aborted) setInspection(entries);
      }
    } catch (e) {
      if (!controller.signal.aborted)
        setError(
          e instanceof Error ? e.message : "Could not load the comparison.",
        );
    } finally {
      if (!controller.signal.aborted) setOpening(false);
    }
  }
  async function decide(
    mapping: IdentityMapping[] | null,
    removed: string[],
    reason: string,
    ackMetadata: boolean,
  ) {
    if (!comparison) return;
    const { revision } = comparison;
    if (api) {
      const args =
        mapping === null
          ? { p_revision_id: revision.id, p_reason: reason }
          : {
              p_revision_id: revision.id,
              p_mapping: mapping,
              p_removed: removed,
              p_reason: reason,
              p_ack_metadata: ackMetadata,
            };
      const { data, error } = await api.rpc(
        mapping === null ? "reject_revision" : "accept_revision",
        args,
      );
      if (error)
        throw Error(
          error.code === "PT409"
            ? "The published source changed. Close this comparison and reload before reviewing again."
            : "Could not confirm this decision. Reload before retrying.",
        );
      revisionSchema.parse(data);
    } else
      onDemoDecision(
        revision.candidate_import_id,
        revision.base_import_id,
        mapping,
      );
    setComparison(null);
    setEvidence(null);
    setRefresh((n) => n + 1);
    onChanged();
    setNotice(
      mapping === null
        ? "Candidate rejected. The published source is unchanged."
        : "Published source updated. Earlier evidence and decisions remain in history.",
    );
    heading.current?.focus();
  }
  function showEvidence(row: Entry, trigger: HTMLButtonElement) {
    evidenceTrigger.current = trigger;
    setEvidence({ ...row });
  }
  return (
    <section className="page imports-page">
      <span className="eyebrow">IMMUTABLE EVIDENCE · EXPLICIT REVISIONS</span>
      <h1 ref={heading} tabIndex={-1}>
        Imports & parser versions
      </h1>
      <p className="view-help">
        Review alternate files and parser versions before changing a bill’s
        published source. Earlier extractions and decisions stay in history.
      </p>
      {!api && (
        <p className="demo-notice">
          Synthetic demo. Candidates use explicit manual identity decisions;
          live matching also checks stored provenance. Changes reset on reload.
        </p>
      )}
      <details className="import-help">
        <summary>Import or reparse a statement</summary>
        <p>
          PDF extraction remains local. Import through the trusted CLI, then
          review candidates here. Browser PDF upload is not part of this
          release.
        </p>
        <code>
          uv run python -m core import-pdf --owner OWNER_UUID --card CARD_UUID
          data/statement.pdf
        </code>
        <br />
        <code>
          uv run python -m core reparse-import --owner OWNER_UUID --import-id
          IMPORT_UUID
        </code>
      </details>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="demo-notice">
          {notice}
        </p>
      )}
      <div className="ledger-heading">
        <h2>Statement imports</h2>
        <button
          type="button"
          disabled={loading || opening}
          onClick={() => setRefresh((n) => n + 1)}
        >
          Reload imports
        </button>
      </div>
      {loading && <p role="status">Loading imports…</p>}
      {opening && <p role="status">Loading source comparison…</p>}
      {!loading && !sources.length && !error && (
        <p className="empty">
          No imports yet. Import a statement locally to get started.
        </p>
      )}
      <div className="source-list">
        {sources.map((source) => (
          <article key={source.id} className="ledger source-card">
            <div>
              <h3>{source.card_label}</h3>
              <p>
                {source.parsed_statement_date ??
                  "Printed statement date unknown"}{" "}
                · {source.entry_count} entries
              </p>
              <small>
                {source.source_filename} · Parser {source.parser_version}
              </small>
            </div>
            <strong className="source-state">{source.state}</strong>
            <div className="form-actions">
              <button
                type="button"
                disabled={opening || loading}
                onClick={() => void open(source, false)}
              >
                Inspect extraction
              </button>
              {source.state === "candidate" && (
                <button
                  type="button"
                  disabled={opening || loading}
                  onClick={() => void open(source, true)}
                >
                  Review candidate
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
      {comparison && (
        <RevisionReview
          key={comparison.revision.id}
          {...comparison}
          sources={sources}
          onAccept={(mapping, removed, reason, ack) =>
            decide(mapping, removed, reason, ack)
          }
          onReject={(reason) => decide(null, [], reason, false)}
          onClose={() => {
            setComparison(null);
            setEvidence(null);
            heading.current?.focus();
          }}
          onEvidence={showEvidence}
        />
      )}
      {inspection && (
        <SourceTable
          title="Original extracted entries"
          rows={inspection}
          onEvidence={showEvidence}
        />
      )}
      {evidence && (
        <Evidence
          key={evidence.id}
          row={evidence}
          api={api}
          onClose={() => {
            setEvidence(null);
            evidenceTrigger.current?.focus();
          }}
        />
      )}
    </section>
  );
}
