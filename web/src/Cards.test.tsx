// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Cards from "./Cards";
import { type Card } from "./useCards";

const card: Card = {
  id: "card",
  label: "Travel",
  bank: "hdfc",
  last_four: "0042",
  version: 1,
  has_statements: true,
};
afterEach(cleanup);
function setup(onSave = vi.fn().mockResolvedValue(card)) {
  const busy = vi.fn();
  render(
    <Cards
      cards={[card]}
      loading={false}
      error=""
      onSave={onSave}
      onReload={vi.fn()}
      onBusyChange={busy}
    />,
  );
  return { user: userEvent.setup(), onSave, busy };
}
it("adds a card with optional digits and resets the form after saving", async () => {
  const { user, onSave, busy } = setup();
  await user.type(screen.getByLabelText("Card name"), "Everyday");
  await user.selectOptions(
    screen.getByLabelText("Bank", { exact: true }),
    "sbi",
  );
  await user.click(screen.getByRole("button", { name: "Add card" }));
  expect(onSave).toHaveBeenCalledWith({
    id: null,
    label: "Everyday",
    bank: "sbi",
    last_four: null,
    version: 0,
  });
  expect((screen.getByLabelText("Card name") as HTMLInputElement).value).toBe(
    "",
  );
  expect(screen.getByRole("status").textContent).toContain("Card added");
  expect(busy.mock.calls).toEqual([[true], [false]]);
});
it("edits a used card and locks its bank; cancel restores add mode", async () => {
  const { user, onSave } = setup();
  await user.click(screen.getByRole("button", { name: "Edit Travel" }));
  expect(
    (screen.getByLabelText("Bank", { exact: true }) as HTMLSelectElement)
      .disabled,
  ).toBe(true);
  expect(
    (screen.getByLabelText("Last four digits (optional)") as HTMLInputElement)
      .value,
  ).toBe("0042");
  await user.clear(screen.getByLabelText("Card name"));
  await user.type(screen.getByLabelText("Card name"), "Holiday");
  await user.click(screen.getByRole("button", { name: "Save changes" }));
  expect(onSave).toHaveBeenCalledWith({
    id: "card",
    label: "Holiday",
    bank: "hdfc",
    last_four: "0042",
    version: 1,
  });
  await user.click(screen.getByRole("button", { name: "Edit Travel" }));
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(
    (screen.getByLabelText("Bank", { exact: true }) as HTMLSelectElement)
      .disabled,
  ).toBe(false);
  expect(screen.getByRole("button", { name: "Add card" })).toBeTruthy();
});
it("preserves edits and shows an error when the save is not confirmed", async () => {
  const { user } = setup(
    vi.fn().mockRejectedValue(Error("Card changed; reload before saving.")),
  );
  await user.click(screen.getByRole("button", { name: "Edit Travel" }));
  await user.type(screen.getByLabelText("Card name"), " updated");
  await user.click(screen.getByRole("button", { name: "Save changes" }));
  expect((await screen.findByRole("alert")).textContent).toContain(
    "Card changed",
  );
  expect((screen.getByLabelText("Card name") as HTMLInputElement).value).toBe(
    "Travel updated",
  );
});
