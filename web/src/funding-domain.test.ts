import { expect, it } from "vitest";
import { demoEntries } from "./demo";
import {
  cents,
  decimalText,
  demoContribution,
  demoFundingGroups,
  demoPreview,
  fundingMoney,
} from "./funding-domain";
import type { Label } from "./useLabels";
const account: Label = {
  id: "11111111-1111-4111-8111-111111111111",
  kind: "account",
  name: "Synthetic pot",
  is_archived: false,
  version: 1,
};
const rows = demoEntries
  .filter((r) => r.card_id === "demo-card-4")
  .map((r) => ({ ...r, account_id: account.id }));
const scope = {
  card_id: "demo-card-4",
  account_id: account.id,
  currency: "INR",
  month: "2026-02-01",
};
const draft = {
  id: "22222222-2222-4222-8222-222222222222",
  amount: "100.00",
  received_on: "2026-02-01",
  note: "Synthetic",
};
it("keeps exact signed currency values beyond floating point precision", () => {
  expect(decimalText(cents("999999999999999999.99"))).toBe(
    "999999999999999999.99",
  );
  expect(fundingMoney("-0.01", "USD")).toBe("− USD 0.01");
  expect(() => cents("1.001")).toThrow();
});
it("allocates contributions oldest first and retains original statement months", () => {
  const initial = demoFundingGroups(rows, [account], [], []);
  const receipt = demoContribution(
    initial,
    scope,
    draft,
    demoPreview(initial, scope).token,
  );
  expect(receipt.applications.map((a) => [a.month, a.amount])).toEqual([
    ["2026-01-01", "100.00"],
  ]);
  const groups = demoFundingGroups(rows, [account], [receipt], []);
  expect(groups.find((g) => g.month === "2026-01-01")?.outstanding).toBe(
    "199.00",
  );
  const full = demoContribution(
    groups,
    scope,
    { ...draft, id: crypto.randomUUID(), amount: null },
    demoPreview(groups, scope).token,
  );
  expect(full.amount).toBe("1119.00");
  expect(full.applications.map((a) => [a.month, a.amount])).toEqual([
    ["2026-01-01", "199.00"],
    ["2026-02-01", "920.00"],
  ]);
});
it("retains disappeared obligations, receipts and correction review flags", () => {
  const groups = demoFundingGroups(rows, [account], [], []);
  const receipt = demoContribution(
    groups,
    scope,
    draft,
    demoPreview(groups, scope).token,
  );
  const changed = demoFundingGroups(
    rows.map((r) => ({ ...r, account_id: null })),
    [account],
    [receipt],
    [],
  );
  const original = changed.find((g) => g.account_id === account.id)!;
  expect(original.net).toBe("0.00");
  expect(original.received).toBe("100.00");
  expect(original.credit).toBe("100.00");
  expect(original.needs_review).toBe(true);
  expect(() =>
    demoContribution(changed, scope, draft, demoPreview(changed, scope).token),
  ).toThrow();
});
it("does not offset arrears with another month's negative spend or another currency", () => {
  const changed = rows.map((r, i) =>
    i ? { ...r, direction: "credit" as const, entry_type: "refund" } : r,
  );
  const groups = demoFundingGroups(changed, [account], [], []);
  const receipt = demoContribution(
    groups,
    scope,
    { ...draft, amount: null },
    demoPreview(groups, scope).token,
  );
  expect(receipt.amount).toBe("299.00");
  expect(receipt.applications).toHaveLength(1);
  expect(() =>
    demoContribution(
      groups,
      { ...scope, currency: "USD" },
      draft,
      demoPreview(groups, scope).token,
    ),
  ).toThrow();
});
