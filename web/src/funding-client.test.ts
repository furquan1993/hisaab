import { expect, it, vi } from "vitest";
import type { BrowserClient } from "./client";
import {
  FundingError,
  readFunding,
  recordContribution,
} from "./funding-client";
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
it("reports a read timeout instead of suggesting missing migrations or credentials", async () => {
  const query = {
    select: vi.fn().mockReturnThis(),
    or: vi.fn().mockReturnThis(),
    order: vi.fn().mockReturnThis(),
    range: vi.fn().mockReturnThis(),
    abortSignal: vi
      .fn()
      .mockResolvedValue({ data: null, error: { code: "57014" } }),
  };
  const api = { from: vi.fn().mockReturnValue(query) };
  await expect(
    readFunding(
      api as unknown as BrowserClient,
      "2026-01-01",
      new AbortController().signal,
    ),
  ).rejects.toThrow("Reconciliation took too long");
});
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
it("uses the transaction API without sending a caller-provided amount", async () => {
  const api = {
    rpc: vi.fn().mockResolvedValue({ data: null, error: { code: "PT409" } }),
  };
  await recordContribution(
    api as unknown as BrowserClient,
    scope,
    { ...draft, amount: null, entry_ids: ["entry"] },
    "state",
    "owner",
  ).catch(() => {});
  expect(api.rpc.mock.calls[0][0]).toBe("record_transaction_contribution");
  expect(api.rpc.mock.calls[0][1]).toMatchObject({
    p_entry_ids: ["entry"],
    p_expected_token: "state",
  });
  expect(api.rpc.mock.calls[0][1]).not.toHaveProperty("p_amount");
});
