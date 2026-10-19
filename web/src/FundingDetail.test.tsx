// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { BrowserClient } from "./client";
import FundingDetail from "./FundingDetail";
import {
  FundingError,
  loadFundingDetail,
  recordContribution,
} from "./funding-client";
import type { FundingPreview } from "./funding-domain";
vi.mock("./funding-client", async (original) => ({
  ...(await original<typeof import("./funding-client")>()),
  loadFundingDetail: vi.fn(),
  recordContribution: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
const scope = {
  card_id: "card",
  account_id: "account",
  currency: "INR",
  month: "2026-01-01",
};
const preview: FundingPreview = {
  token: "captured-state",
  groups: [
    {
      month: "2026-01-01",
      net: "100.00",
      received: "0.00",
      outstanding: "100.00",
      credit: "0.00",
      fingerprint: "source",
      blocked: false,
      needs_review: false,
    },
  ],
};
async function setup() {
  vi.mocked(loadFundingDetail).mockResolvedValue({ preview, history: [] });
  const changed = vi.fn(),
    busy = vi.fn(),
    user = userEvent.setup();
  render(
    <FundingDetail
      api={{} as BrowserClient}
      ownerId="owner"
      scope={scope}
      cardLabel="Synthetic card"
      accountName="Synthetic account"
      demoGroups={[]}
      demoReceipts={[]}
      onDemoReceipt={vi.fn()}
      onDemoConfirm={vi.fn()}
      onChanged={changed}
      onClose={vi.fn()}
      onBusyChange={busy}
    />,
  );
  await screen.findByText("Outstanding: INR 100.00");
  return { user, changed, busy };
}
it("retries an uncertain contribution with the same immutable request and captured state", async () => {
  const { user, changed, busy } = await setup();
  vi.mocked(recordContribution).mockRejectedValueOnce(Error("Connection lost"));
  await user.type(screen.getByLabelText("Partial contribution amount"), "25");
  await user.click(
    screen.getByRole("button", { name: "Record partial contribution" }),
  );
  expect(screen.getByRole("alert").textContent).toContain(
    "Retry the same request",
  );
  expect(
    (
      screen.getByRole("button", {
        name: "Close contributions",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  vi.mocked(recordContribution).mockResolvedValueOnce({
    id: crypto.randomUUID(),
    ...scope,
    amount: "25.00",
    received_on: "2026-01-01",
    note: "",
    applications: [],
    created_at: "2026-01-01T00:00:00Z",
  });
  await user.click(
    screen.getByRole("button", { name: "Retry same contribution" }),
  );
  const calls = vi.mocked(recordContribution).mock.calls;
  expect(calls).toHaveLength(2);
  expect(calls[0][2]).toEqual(calls[1][2]);
  expect(calls[0][3]).toBe(calls[1][3]);
  expect(changed).toHaveBeenCalledTimes(1);
  await waitFor(() => expect(busy).toHaveBeenLastCalledWith(false));
});
it("keeps the draft editable after a definite server rejection", async () => {
  const { user, busy } = await setup();
  vi.mocked(recordContribution).mockRejectedValueOnce(
    new FundingError("Balances changed"),
  );
  await user.type(screen.getByLabelText("Partial contribution amount"), "25");
  await user.click(
    screen.getByRole("button", { name: "Record partial contribution" }),
  );
  expect(
    (screen.getByLabelText("Partial contribution amount") as HTMLInputElement)
      .value,
  ).toBe("25");
  expect(
    (screen.getByLabelText("Partial contribution amount") as HTMLInputElement)
      .disabled,
  ).toBe(false);
  expect(
    screen.queryByRole("button", { name: "Retry same contribution" }),
  ).toBeNull();
  expect(busy).toHaveBeenLastCalledWith(false);
});
