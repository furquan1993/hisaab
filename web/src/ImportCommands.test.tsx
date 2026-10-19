// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ImportCommands from "./ImportCommands";
import type { BrowserClient } from "./client";

afterEach(cleanup);
const owner = "11111111-1111-4111-8111-111111111111";
const firstCard = "22222222-2222-4222-8222-222222222222";
const secondCard = "33333333-3333-4333-8333-333333333333";
function apiResult(data: unknown, error: unknown = null) {
  const query = {
    select: vi.fn().mockReturnThis(),
    order: vi.fn().mockReturnThis(),
    range: vi.fn().mockReturnThis(),
    abortSignal: vi.fn().mockResolvedValue({ data, error }),
  };
  const from = vi.fn().mockReturnValue(query);
  return { api: { from } as unknown as BrowserClient, from, query };
}

it("fills the owner and card UUIDs, deduplicates cards, and updates the command when switching cards", async () => {
  const user = userEvent.setup();
  const first = { card_id: firstCard, card_label: "First card" };
  const { api, from, query } = apiResult([
    first,
    first,
    { card_id: secondCard, card_label: "Second card" },
  ]);
  render(<ImportCommands api={api} ownerId={owner} sources={[]} />);
  const select = await screen.findByLabelText("Card to import into");
  expect(from).toHaveBeenCalledWith("statement_bills");
  expect(query.select).toHaveBeenCalledWith("card_id,card_label");
  expect(screen.getAllByRole("option")).toHaveLength(2);
  expect(
    screen.getByText(
      `uv run python -m core import-pdf --owner ${owner} --card ${firstCard} data/statement.pdf`,
    ),
  ).toBeTruthy();
  await user.selectOptions(select, secondCard);
  expect(
    screen.getByText(
      `uv run python -m core import-pdf --owner ${owner} --card ${secondCard} data/statement.pdf`,
    ),
  ).toBeTruthy();
  expect(document.body.textContent).not.toContain("OWNER_UUID");
  expect(document.body.textContent).not.toContain("CARD_UUID");
});

it("does not show an incomplete command when no card IDs are available", async () => {
  const { api } = apiResult([]);
  const { container } = render(
    <ImportCommands api={api} ownerId={owner} sources={[]} />,
  );
  await screen.findByText(/No card IDs available/);
  expect(container.querySelector("code")).toBeNull();
});

it("shows a loading failure without inventing UUIDs", async () => {
  const { api } = apiResult(null, { code: "offline" });
  const { container } = render(
    <ImportCommands api={api} ownerId={owner} sources={[]} />,
  );
  expect((await screen.findByRole("alert")).textContent).toContain(
    "Could not load cards",
  );
  expect(container.querySelector("code")).toBeNull();
});
