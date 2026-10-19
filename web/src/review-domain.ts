import type { Entry } from "./domain";
export const reviewFields = [
  "transaction_date",
  "transaction_time",
  "description",
  "amount",
  "direction",
  "currency",
  "entry_type",
] as const;
export type ReviewField = (typeof reviewFields)[number];
export type ReviewPatch = Partial<Record<ReviewField, string | null>>;
export function issueKey(issue: { code: string; [key: string]: unknown }) {
  return issue.code + ":" + (issue.page ?? "");
}
export const criticalIssues = new Set([
  "date_missing_or_invalid",
  "time_missing_or_invalid",
  "amount_unreadable",
  "amount_missing_or_invalid",
  "direction_ambiguous",
  "direction_missing_or_unknown",
  "currency_unknown",
  "currency_missing_or_unknown",
  "description_missing",
  "entry_type_unknown",
  "entry_type_direction_conflict",
  "statement_date_missing_or_invalid",
  "statement_date_conflict",
]);
export function reviewedValues(row: Entry) {
  return {
    transaction_date:
      row.effective_transaction_date === undefined
        ? row.transaction_date
        : row.effective_transaction_date,
    transaction_time:
      row.effective_transaction_time === undefined
        ? (row.original_transaction_time ?? null)
        : row.effective_transaction_time,
    description: row.effective_description ?? row.description,
    amount:
      row.effective_amount === undefined ? row.amount : row.effective_amount,
    direction:
      row.effective_direction === undefined
        ? row.direction
        : row.effective_direction,
    currency:
      row.effective_currency === undefined
        ? row.currency
        : row.effective_currency,
    entry_type: row.effective_entry_type ?? row.entry_type,
  };
}
export function demoSignature(row: Entry) {
  return JSON.stringify([
    row.transaction_date,
    row.original_transaction_time ?? null,
    row.description,
    row.amount,
    row.direction,
    row.currency,
    row.entry_type,
    row.entry_issues,
  ]);
}
export function requiresReview(row: Entry) {
  const values = reviewedValues(row);
  const statement =
    row.effective_statement_date === undefined
      ? row.statement_date
      : row.effective_statement_date;
  return (
    !row.is_selected ||
    !values.transaction_date ||
    !statement ||
    values.amount === null ||
    !values.direction ||
    !values.currency ||
    !values.description.trim() ||
    values.entry_type === "unknown" ||
    (["payment", "cashback"].includes(values.entry_type) &&
      values.direction !== "credit") ||
    (row.unresolved_entry_issues ?? row.entry_issues).length > 0 ||
    (row.unresolved_import_issues ?? row.import_issues).length > 0 ||
    row.review_stale ||
    row.import_review_stale
  );
}
export function applyDemoReview(
  row: Entry,
  patch: ReviewPatch,
  ack: string[],
): Entry {
  if (
    ack.some(
      (key) =>
        !row.entry_issues.some(
          (issue) => issueKey(issue) === key && !criticalIssues.has(issue.code),
        ),
    )
  )
    throw Error(
      "Correct missing or invalid facts instead of acknowledging them.",
    );
  const overrides = { ...(row.review_stale ? {} : row.overrides) };
  for (const field of reviewFields)
    if (field in patch) {
      if (patch[field] === null) delete overrides[field];
      else overrides[field] = patch[field]!;
    }
  if (overrides.amount) {
    if (!/^[0-9]{1,18}([.][0-9]{1,2})?$/.test(overrides.amount))
      throw Error("Use a decimal amount with at most two places.");
    const [whole, fraction = ""] = overrides.amount.split(".");
    overrides.amount = BigInt(whole).toString() + "." + fraction.padEnd(2, "0");
  }
  const values = {
    transaction_date: row.transaction_date,
    transaction_time: row.original_transaction_time ?? null,
    description: row.description,
    amount: row.amount,
    direction: row.direction,
    currency: row.currency,
    entry_type: row.entry_type,
    ...overrides,
  };
  const unresolved = row.entry_issues.filter((issue) => {
    if (ack.includes(issueKey(issue))) return false;
    const field: Record<string, ReviewField> = {
      date_missing_or_invalid: "transaction_date",
      time_missing_or_invalid: "transaction_time",
      description_missing: "description",
      amount_unreadable: "amount",
      amount_missing_or_invalid: "amount",
      direction_ambiguous: "direction",
      direction_missing_or_unknown: "direction",
      currency_unknown: "currency",
      currency_missing_or_unknown: "currency",
    };
    if (issue.code === "entry_type_unknown")
      return values.entry_type === "unknown";
    if (issue.code === "entry_type_direction_conflict")
      return (
        ["payment", "cashback"].includes(values.entry_type) &&
        values.direction !== "credit"
      );
    return !field[issue.code] || !values[field[issue.code]];
  });
  const next: Entry = {
    ...row,
    overrides,
    applied_overrides: overrides,
    applied_acknowledged: ack,
    review_stale: false,
    demo_review_signature: demoSignature(row),
    decision_version: row.decision_version + 1,
    effective_transaction_date: values.transaction_date,
    effective_transaction_time: values.transaction_time,
    effective_description: values.description,
    effective_amount: values.amount,
    effective_direction: values.direction as Entry["direction"],
    effective_currency: values.currency,
    effective_entry_type: values.entry_type,
    unresolved_entry_issues: unresolved,
    needs_review: row.needs_review,
  };
  return { ...next, needs_review: requiresReview(next) };
}
