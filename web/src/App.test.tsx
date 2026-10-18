// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
afterEach(cleanup);
it("opens an explicitly synthetic demo and switches independent date views", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  );
  expect(screen.getByText("Weekend bookstore")).toBeTruthy();
  await user.click(screen.getByRole("tab", { name: "Transaction date" }));
  expect(screen.queryByText("Weekend bookstore")).toBeNull();
  expect(screen.getByText("Late-posted train ticket")).toBeTruthy();
  await user.click(screen.getByRole("tab", { name: "Needs review" }));
  expect(screen.getByText("Tax • no printed date")).toBeTruthy();
  expect(screen.getByText("Corner coffee • alternate file")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Exit demo" }));
  expect(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  ).toBeTruthy();
  expect(screen.queryByText("Tax • no printed date")).toBeNull();
});
it("renders evidence as text without offering fake PDF downloads", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  );
  await user.click(screen.getAllByRole("button", { name: "View evidence" })[0]);
  expect(
    screen.getByRole("complementary", { name: "Source evidence" }),
  ).toBeTruthy();
  expect(
    screen.queryByRole("button", { name: "Download original PDF" }),
  ).toBeNull();
});
