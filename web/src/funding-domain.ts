import { z } from "zod";
import type { Entry } from "./domain";
import { reviewedValues } from "./review-domain";
import type { Label } from "./useLabels";

const decimal = z.string().regex(/^-?\d+\.\d{2}$/);
export const fundingGroupSchema = z.object({
  card_id: z.string(),
  card_label: z.string(),
  account_id: z.string().nullable(),
  account_name: z.string().nullable(),
  currency: z.string().nullable(),
  month: z.string().nullable(),
  net: decimal,
  received: decimal,
  outstanding: decimal,
  credit: decimal,
  entry_count: z.number().int().nonnegative(),
  fingerprint: z.string(),
  blocked: z.boolean(),
  needs_review: z.boolean(),
});
export type FundingGroup = z.infer<typeof fundingGroupSchema>;
export const applicationSchema = z.object({
  month: z.string(),
  amount: decimal,
  fingerprint: z.string(),
});
export const contributionSchema = z.object({
  id: z.string().uuid(),
  card_id: z.string(),
  account_id: z.string(),
  currency: z.string(),
  month: z.string(),
  amount: decimal,
  received_on: z.string(),
  note: z.string(),
  applications: z.array(applicationSchema),
  created_at: z.string(),
});
export type Contribution = z.infer<typeof contributionSchema>;
export type Confirmation = {
  card_id: string;
  account_id: string;
  currency: string;
  month: string;
  fingerprint: string;
  created_at: string;
};
export const previewSchema = z.object({
  token: z.string(),
  groups: z.array(
    fundingGroupSchema
      .pick({
        month: true,
        net: true,
        received: true,
        outstanding: true,
        credit: true,
        fingerprint: true,
        blocked: true,
        needs_review: true,
      })
      .extend({ month: z.string() }),
  ),
});
export type FundingPreview = z.infer<typeof previewSchema>;
export type FundingScope = {
  card_id: string;
  account_id: string;
  currency: string;
  month: string;
};
export type ContributionDraft = {
  id: string;
  amount: string | null;
  received_on: string;
  note: string;
};
export const attentionSchema = z.object({
  id: z.string(),
  card_label: z.string(),
  effective_statement_date: z.string().nullable(),
  reason: z.string(),
});
export type FundingAttention = z.infer<typeof attentionSchema>;

export function cents(value: string): bigint {
  if (!/^-?\d+(\.\d{1,2})?$/.test(value))
    throw Error("Use a decimal amount with at most two places.");
  const [whole, fraction = ""] = value.replace("-", "").split(".");
  return (
    (BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"))) *
    (value.startsWith("-") ? -1n : 1n)
  );
}
export function decimalText(value: bigint) {
  const absolute = value < 0n ? -value : value;
  return `${value < 0n ? "-" : ""}${absolute / 100n}.${String(absolute % 100n).padStart(2, "0")}`;
}
export function fundingMoney(value: string, currency: string | null) {
  const amount = cents(value),
    absolute = amount < 0n ? -amount : amount;
  return `${amount < 0n ? "− " : ""}${currency ?? "?"} ${new Intl.NumberFormat("en-IN").format(absolute / 100n)}.${String(absolute % 100n).padStart(2, "0")}`;
}
export function sameScope(
  group: Pick<FundingGroup, "card_id" | "account_id" | "currency">,
  scope: FundingScope,
) {
  return (
    group.card_id === scope.card_id &&
    group.account_id === scope.account_id &&
    group.currency === scope.currency
  );
}
export function demoPreview(
  groups: FundingGroup[],
  scope: FundingScope,
): FundingPreview {
  const items = groups
    .filter((g) => sameScope(g, scope) && g.month && g.month <= scope.month)
    .sort((a, b) => a.month!.localeCompare(b.month!))
    .map((g) => ({
      month: g.month!,
      net: g.net,
      received: g.received,
      outstanding: g.outstanding,
      credit: g.credit,
      fingerprint: g.fingerprint,
      blocked: g.blocked,
      needs_review: g.needs_review,
    }));
  return { token: JSON.stringify(items), groups: items };
}

// Demo-only mirror. Live financial aggregation and allocation are enforced by SQL.
export function demoFundingGroups(
  rows: Entry[],
  labels: Label[],
  receipts: Contribution[],
  confirmations: Confirmation[],
): FundingGroup[] {
  const groups = new Map<string, FundingGroup>();
  const records = new Map<string, unknown[]>();
  const key = (g: {
    card_id: string;
    account_id: string | null;
    currency: string | null;
    month: string | null;
  }) => JSON.stringify([g.card_id, g.account_id, g.currency, g.month]);
  const get = (
    scope: {
      card_id: string;
      account_id: string | null;
      currency: string | null;
      month: string | null;
    },
    label: string,
  ) => {
    const id = key(scope);
    let group = groups.get(id);
    if (!group) {
      group = {
        ...scope,
        card_label: label,
        account_name:
          labels.find((l) => l.kind === "account" && l.id === scope.account_id)
            ?.name ?? null,
        net: "0.00",
        received: "0.00",
        outstanding: "0.00",
        credit: "0.00",
        entry_count: 0,
        fingerprint: "empty:" + id,
        blocked: !scope.account_id || !scope.currency || !scope.month,
        needs_review: false,
      };
      groups.set(id, group);
    }
    return group;
  };
  for (const row of rows) {
    const values = reviewedValues(row);
    if (!row.is_selected || values.entry_type === "payment") continue;
    const card = row.card_id ?? row.card_label;
    const date =
      row.effective_statement_date === undefined
        ? row.statement_date
        : row.effective_statement_date;
    const scope = {
      card_id: card,
      account_id: row.account_id,
      currency: values.currency,
      month: date ? date.slice(0, 7) + "-01" : null,
    };
    const group = get(scope, row.card_label);
    group.net = decimalText(
      cents(group.net) +
        (values.amount && values.direction
          ? cents(values.amount) * (values.direction === "debit" ? 1n : -1n)
          : 0n),
    );
    group.entry_count++;
    const list = records.get(key(scope)) ?? [];
    list.push([
      row.id,
      row.import_id,
      row.decision_version,
      values,
      row.import_review_version,
      row.needs_review,
    ]);
    records.set(key(scope), list);
    group.fingerprint = JSON.stringify(list);
  }
  for (const receipt of receipts)
    for (const application of receipt.applications) {
      const group = get(
        { ...receipt, month: application.month },
        rows.find((r) => (r.card_id ?? r.card_label) === receipt.card_id)
          ?.card_label ?? receipt.card_id,
      );
      group.received = decimalText(
        cents(group.received) + cents(application.amount),
      );
    }
  for (const confirmation of confirmations)
    get(
      confirmation,
      rows.find((r) => (r.card_id ?? r.card_label) === confirmation.card_id)
        ?.card_label ?? confirmation.card_id,
    );
  for (const group of groups.values()) {
    const events = [
      ...receipts.flatMap((r) =>
        r.applications
          .filter((a) => sameScope(group, r) && a.month === group.month)
          .map((a) => ({ ...a, created_at: r.created_at })),
      ),
      ...confirmations.filter(
        (c) => sameScope(group, c) && c.month === group.month,
      ),
    ].sort((a, b) => a.created_at.localeCompare(b.created_at));
    const last = events.at(-1);
    group.needs_review = !!last && last.fingerprint !== group.fingerprint;
    const due = cents(group.net) > 0n ? cents(group.net) : 0n,
      received = cents(group.received);
    group.outstanding = decimalText(due > received ? due - received : 0n);
    group.credit = decimalText(received > due ? received - due : 0n);
    group.blocked ||= rows.some((r) => {
      if (
        (r.card_id ?? r.card_label) !== group.card_id ||
        r.source_state === "rejected" ||
        r.source_state === "superseded"
      )
        return false;
      const date =
        r.effective_statement_date === undefined
          ? r.statement_date
          : r.effective_statement_date;
      if (date && date.slice(0, 7) !== group.month?.slice(0, 7)) return false;
      return (
        !r.is_selected ||
        r.needs_review ||
        (reviewedValues(r).entry_type !== "payment" &&
          (!r.account_id || !reviewedValues(r).currency))
      );
    });
  }
  return [...groups.values()];
}
export function demoContribution(
  groups: FundingGroup[],
  scope: FundingScope,
  draft: ContributionDraft,
  token: string,
): Contribution {
  const preview = demoPreview(groups, scope);
  if (preview.token !== token)
    throw Error("Balances changed. Reload and review before contributing.");
  if (
    !preview.groups.length ||
    preview.groups.some((g) => g.blocked || g.needs_review)
  )
    throw Error("Resolve or confirm affected months first.");
  const total = preview.groups.reduce(
    (sum, g) => sum + cents(g.outstanding),
    0n,
  );
  let remaining = draft.amount === null ? total : cents(draft.amount);
  if (remaining <= 0n || remaining > total)
    throw Error(
      "Contribution must be positive and no greater than the outstanding balance.",
    );
  const amount = decimalText(remaining),
    applications: Contribution["applications"] = [];
  for (const group of preview.groups) {
    const part =
      remaining < cents(group.outstanding)
        ? remaining
        : cents(group.outstanding);
    if (part > 0n) {
      applications.push({
        month: group.month,
        amount: decimalText(part),
        fingerprint: group.fingerprint,
      });
      remaining -= part;
    }
  }
  return {
    ...scope,
    ...draft,
    amount,
    applications,
    created_at: new Date().toISOString(),
  };
}
