import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { downloadOriginal, evidenceSchema, type BrowserClient } from "./client";
import type { Entry } from "./domain";

export default function Evidence({
  row,
  api,
  onClose,
}: {
  row: Entry;
  api: BrowserClient | null;
  onClose: () => void;
}) {
  const [data, setData] = useState<z.infer<typeof evidenceSchema> | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  // Focus scrolls the selected evidence into view, including when it is below
  // a long statement table. Reopening the same row refocuses without refetching.
  // https://react.dev/reference/react/useRef#manipulating-the-dom-with-a-ref
  useEffect(() => {
    heading.current?.focus();
  }, [row]);
  useEffect(() => {
    setData(null);
    setError("");
    if (!api) return;
    const controller = new AbortController();
    api
      .from("entry_evidence")
      .select("*")
      .eq("id", row.id)
      .abortSignal(controller.signal)
      .single()
      .then(({ data, error }) => {
        if (controller.signal.aborted) return;
        const checked = evidenceSchema.safeParse(data);
        if (error || !checked.success)
          setError("Evidence could not be loaded.");
        else setData(checked.data);
      });
    return () => controller.abort();
  }, [api, row.id]);
  async function download() {
    if (!api) return;
    setBusy(true);
    setError("");
    try {
      await downloadOriginal(api, row.import_id);
    } catch {
      setError(
        "Original unavailable or integrity check failed. No file was downloaded.",
      );
    } finally {
      setBusy(false);
    }
  }
  const issues = [...row.entry_issues, ...row.import_issues];
  return (
    <aside
      id="source-evidence"
      className="evidence"
      aria-label="Source evidence"
    >
      <div className="section-head">
        <div>
          <span className="eyebrow">ORIGINAL EVIDENCE</span>
          <h2 ref={heading} tabIndex={-1}>
            {row.description}
          </h2>
        </div>
        <button onClick={onClose} aria-label="Close evidence">
          ×
        </button>
      </div>
      <dl>
        <div>
          <dt>Card</dt>
          <dd>{row.card_label}</dd>
        </div>
        <div>
          <dt>Statement date</dt>
          <dd>{row.statement_date ?? "Not printed"}</dd>
        </div>
        <div>
          <dt>Transaction date</dt>
          <dd>{row.transaction_date ?? "Unknown • needs review"}</dd>
        </div>
        <div>
          <dt>Entry type</dt>
          <dd>{row.entry_type}</dd>
        </div>
        <div>
          <dt>Source selection</dt>
          <dd>
            {row.is_selected ? "Selected import" : "Unselected candidate"}
          </dd>
        </div>
      </dl>
      {issues.length > 0 && (
        <div className="notice">
          <strong>Preserved issues</strong>
          <ul>
            {issues.map((issue, i) => (
              <li key={i}>{issue.code.replaceAll("_", " ")}</li>
            ))}
          </ul>
        </div>
      )}
      <h3>Extracted source text</h3>
      <pre>
        {api
          ? (data?.source_raw_text ?? "Loading source…")
          : `SYNTHETIC EXAMPLE ONLY\n${row.transaction_date ?? "[date not printed]"} ${row.description} ${row.amount}`}
      </pre>
      {data && (
        <dl>
          <div>
            <dt>Original filename</dt>
            <dd>{data.source_filename}</dd>
          </div>
          <div>
            <dt>Page / parser</dt>
            <dd>
              {data.source_page} / {data.parser_version}
            </dd>
          </div>
          <div>
            <dt>Raw date / amount</dt>
            <dd>
              {data.raw_date || "Not printed"} /{" "}
              {data.raw_amount || "Not printed"}
            </dd>
          </div>
        </dl>
      )}
      {api && data && data.pdf_deleted_at === null && (
        <button className="primary" disabled={busy} onClick={download}>
          {busy ? "Verifying original…" : "Download original PDF"}
        </button>
      )}
      {!api && (
        <p className="muted">
          Demo evidence is invented. No original PDF exists.
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <p className="muted">
        Source facts are read-only. Review corrections and assignments will be
        added separately.
      </p>
    </aside>
  );
}
