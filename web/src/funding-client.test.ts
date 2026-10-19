import { expect, it, vi } from "vitest";
import type { BrowserClient } from "./client";
import { FundingError, recordContribution } from "./funding-client";
const scope = {
  card_id: "card",
  account_id: "account",
  currency: "INR",
  month: "2026-01-01",
};
const draft = {
  id: "11111111-1111-4111-8111-111111111111",
  amount: "25.00",
  received_on: "2026-01-01",
  note: "",
};
it("does not treat a returned PostgREST fetch failure as a definite rejection", async () => {
  const api = {
    rpc: vi.fn().mockResolvedValue({
      data: null,
      error: { code: "", message: "Failed to fetch" },
    }),
  };
  const error = await recordContribution(
    api as unknown as BrowserClient,
    scope,
    draft,
    "captured-state",
    "owner",
  ).catch((e) => e);
  expect(error).toBeInstanceOf(Error);
  expect(error).not.toBeInstanceOf(FundingError);
  expect(api.rpc.mock.calls[0][1]).toMatchObject({
    p_id: draft.id,
    p_expected_token: "captured-state",
    p_expected_owner: "owner",
  });
});
it("distinguishes a definite database conflict from an uncertain network result", async () => {
  const api = {
    rpc: vi.fn().mockResolvedValue({
      data: null,
      error: { code: "PT409", message: "Changed" },
    }),
  };
  await expect(
    recordContribution(
      api as unknown as BrowserClient,
      scope,
      draft,
      "captured-state",
      "owner",
    ),
  ).rejects.toBeInstanceOf(FundingError);
});
