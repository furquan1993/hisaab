import { z } from "zod";
import type { BrowserClient } from "./client";
import {
  attentionSchema,
  contributionSchema,
  fundingGroupSchema,
  previewSchema,
  type ContributionDraft,
  type FundingScope,
} from "./funding-domain";

async function allPages<T>(
  schema: z.ZodType<T>,
  page: (offset: number) => PromiseLike<{ data: unknown; error: unknown }>,
) {
  const result: T[] = [];
  for (let offset = 0; ; offset += 100) {
    const { data, error } = await page(offset);
    if (error) {
      if (
        typeof error === "object" &&
        "code" in error &&
        error.code === "57014"
      )
        throw Error(
          "Reconciliation took too long to load. Please retry; if it persists, the database query needs attention.",
        );
      throw Error(
        "Could not load reconciliation. Check the connection and approved database upgrade, then reload.",
      );
    }
    const items = z.array(schema).parse(data);
    result.push(...items);
    if (items.length < 100) return result;
  }
}
export async function readFunding(
  api: BrowserClient,
  month: string,
  signal: AbortSignal,
) {
  const [groups, attention] = await Promise.all([
    allPages(fundingGroupSchema, (offset) =>
      api
        .from("funding_groups")
        .select("*")
        .or(`month.lte.${month},month.is.null`)
        .order("card_id")
        .order("account_id")
        .order("currency")
        .order("month")
        .range(offset, offset + 99)
        .abortSignal(signal),
    ),
    allPages(attentionSchema, (offset) =>
      api
        .from("funding_attention")
        .select("*")
        .order("id")
        .range(offset, offset + 99)
        .abortSignal(signal),
    ),
  ]);
  return {
    groups,
    attention: attention.filter(
      (a) =>
        !a.effective_statement_date ||
        a.effective_statement_date.slice(0, 7) <= month.slice(0, 7),
    ),
  };
}
export function scopeArgs(scope: FundingScope, ownerId: string) {
  return {
    p_card_id: scope.card_id,
    p_account_id: scope.account_id,
    p_currency: scope.currency,
    p_month: scope.month,
    p_expected_owner: ownerId,
  };
}
export class FundingError extends Error {}
async function rpc(
  api: BrowserClient,
  name: string,
  args: Record<string, unknown>,
) {
  const { data, error } = await api.rpc(name, args);
  if (error) {
    const message =
      error.code === "PT409"
        ? "Balances or review status changed. Reload this panel and review before retrying."
        : error.code === "PT422"
          ? error.message
          : "Could not confirm the operation.";
    // PostgREST may return a fetch/network failure as an error with an empty code,
    // rather than throwing. Only a definite database rejection releases a request ID.
    if (["PT409", "PT422", "PT404", "42501"].includes(error.code))
      throw new FundingError(message);
    throw new Error(message);
  }
  return data;
}
export async function loadFundingDetail(
  api: BrowserClient,
  scope: FundingScope,
  ownerId: string,
  signal: AbortSignal,
) {
  const [data, history] = await Promise.all([
    rpc(api, "funding_preview", scopeArgs(scope, ownerId)),
    allPages(contributionSchema, (offset) =>
      api
        .from("contributions")
        .select("*")
        .eq("card_id", scope.card_id)
        .eq("account_id", scope.account_id)
        .eq("currency", scope.currency)
        .order("created_at")
        .order("id")
        .range(offset, offset + 99)
        .abortSignal(signal),
    ),
  ]);
  return { preview: previewSchema.parse(data), history };
}
export async function recordContribution(
  api: BrowserClient,
  scope: FundingScope,
  draft: ContributionDraft,
  token: string,
  ownerId: string,
) {
  return contributionSchema.parse(
    await rpc(api, "record_contribution", {
      ...scopeArgs(scope, ownerId),
      p_id: draft.id,
      p_amount: draft.amount,
      p_received_on: draft.received_on,
      p_note: draft.note,
      p_expected_token: token,
    }),
  );
}
export async function confirmFunding(
  api: BrowserClient,
  scope: FundingScope,
  reason: string,
  token: string,
  ownerId: string,
  throughMonth: string = scope.month,
) {
  await rpc(api, "confirm_funding", {
    ...scopeArgs(scope, ownerId),
    p_reason: reason,
    p_expected_token: token,
    p_through_month: throughMonth,
  });
}
