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

it("lists saved cards even without statements and updates the command when switching cards", async () => {
  const user = userEvent.setup();
  const first = { id: firstCard, label: "First card" };
  const { api, from, query } = apiResult([
    first,
    { id: secondCard, label: "New card without statements" },
  ]);
  render(<ImportCommands api={api} ownerId={owner} sources={[]} />);
  const select = await screen.findByLabelText("Card to import into");
  expect(from).toHaveBeenCalledWith("cards");
  expect(query.select).toHaveBeenCalledWith("id,label");
  expect(screen.getAllByRole("option")).toHaveLength(2);
  expect(
    screen.getByRole("option", { name: "New card without statements" }),
  ).toBeTruthy();
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
  render(<ImportCommands api={api} ownerId={owner} sources={[]} />);
  await screen.findByText(/No saved cards yet/);
  expect(screen.queryByText(/uv run python -m core import-pdf/)).toBeNull();
});

it("loads every page of saved cards", async () => {
  const page = Array.from({ length: 100 }, (_, index) => ({
    id: `22222222-2222-4222-8222-${String(index).padStart(12, "0")}`,
    label: `Card ${index}`,
  }));
  const { api, query } = apiResult([]);
  query.abortSignal
    .mockResolvedValueOnce({ data: page, error: null })
    .mockResolvedValueOnce({
      data: [{ id: secondCard, label: "Last card" }],
      error: null,
    });
  render(<ImportCommands api={api} ownerId={owner} sources={[]} />);
  await screen.findByLabelText("Card to import into");
  expect(screen.getAllByRole("option")).toHaveLength(101);
  expect(query.order.mock.calls).toEqual([
    ["label"],
    ["id"],
    ["label"],
    ["id"],
  ]);
  expect(query.range.mock.calls).toEqual([
    [0, 99],
    [100, 199],
  ]);
  await userEvent
    .setup()
    .selectOptions(screen.getByLabelText("Card to import into"), secondCard);
  expect(
    screen.getByText(
      `uv run python -m core import-pdf --owner ${owner} --card ${secondCard} data/statement.pdf`,
    ),
  ).toBeTruthy();
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
