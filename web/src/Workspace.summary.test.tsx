// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Workspace from "./Workspace";
afterEach(cleanup);

it("opens Summary from the sidebar and carries its month and date basis into entries and reconciliation", async () => {
  const user = userEvent.setup();
  render(
    <Workspace
      api={null}
      owner="Demo"
      initialRange={["2026-01-01", "2026-01-31"]}
      onExit={() => {}}
    />,
  );
  await screen.findByText("Weekend bookstore");
  await user.click(screen.getByRole("button", { name: "Summary" }));
  expect(screen.getByRole("heading", { name: "Summary" })).toBeTruthy();
  expect(
    within(
      screen.getByRole("region", { name: "INR spending summary" }),
    ).getAllByText("INR 3,832.35"),
  ).toHaveLength(3);
  await user.selectOptions(screen.getByLabelText("Date basis"), "transaction");
  await user.click(screen.getByRole("button", { name: "View entries" }));
  expect(
    screen
      .getByRole("tab", { name: "Transaction date" })
      .getAttribute("aria-selected"),
  ).toBe("true");
  expect(
    (screen.getByLabelText("Filter dates") as HTMLSelectElement).value,
  ).toBe("reviewed");
  await screen.findByText("Late-posted train ticket");
  expect(screen.queryByText("Weekend bookstore")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Summary" }));
  await user.click(screen.getByRole("button", { name: "Next summary month" }));
  await user.click(screen.getByRole("button", { name: "View reconciliation" }));
  expect(
    (screen.getByLabelText("Reconciliation month") as HTMLSelectElement).value,
  ).toBe("02");
});
