// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
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
it("manages independent Accounts and Categories across workspace navigation", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  );
  await user.click(screen.getByRole("button", { name: "Accounts" }));
  await user.type(screen.getByLabelText("Account name"), "Eating out");
  await user.click(screen.getByRole("button", { name: "Create Account" }));
  expect(screen.getByRole("button", { name: "Edit Eating out" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Categories" }));
  await user.type(screen.getByLabelText("Category name"), "Eating out");
  await user.click(screen.getByRole("button", { name: "Create Category" }));
  await user.click(screen.getByRole("button", { name: "Accounts" }));
  await user.click(screen.getByRole("button", { name: "Edit Eating out" }));
  await user.clear(screen.getByLabelText("Account name"));
  await user.type(screen.getByLabelText("Account name"), "Weekend pot");
  await user.click(screen.getByRole("button", { name: "Save changes" }));
  await user.click(screen.getByRole("button", { name: "Archive Weekend pot" }));
  expect(
    screen.getByRole("button", { name: "Restore Weekend pot" }),
  ).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Categories" }));
  expect(screen.getByRole("button", { name: "Edit Eating out" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Statements" }));
  expect(screen.getByText("Weekend bookstore")).toBeTruthy();
});
it("saves independent entry assignments without clearing a source issue", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  );
  await user.click(screen.getByRole("button", { name: "Accounts" }));
  await user.type(screen.getByLabelText("Account name"), "Household pot");
  await user.click(screen.getByRole("button", { name: "Create Account" }));
  await user.click(screen.getByRole("button", { name: "Categories" }));
  await user.type(screen.getByLabelText("Category name"), "Miscellaneous");
  await user.click(screen.getByRole("button", { name: "Create Category" }));
  await user.click(screen.getByRole("button", { name: "Statements" }));
  await user.click(screen.getByRole("tab", { name: "Needs review" }));
  const row = screen.getByText("Credit • purpose unclear").closest("tr")!;
  await user.click(within(row).getByRole("button", { name: "Edit entry" }));
  await user.selectOptions(
    screen.getByLabelText("Account"),
    screen.getByRole("option", { name: "Household pot" }),
  );
  await user.selectOptions(
    screen.getByLabelText("Category"),
    screen.getByRole("option", { name: "Miscellaneous" }),
  );
  await user.click(screen.getByRole("button", { name: "Save assignments" }));
  const saved = screen.getByText("Credit • purpose unclear").closest("tr")!;
  expect(within(saved).getByText("Household pot")).toBeTruthy();
  expect(within(saved).getByText("Miscellaneous")).toBeTruthy();
  expect(within(saved).getByText("● Needs review")).toBeTruthy();
  await user.click(screen.getByRole("tab", { name: "Statement date" }));
  const persisted = screen.getByText("Credit • purpose unclear").closest("tr")!;
  expect(within(persisted).getByText("Household pot")).toBeTruthy();
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
  expect(document.activeElement).toBe(
    screen.getByRole("heading", { name: "Weekend bookstore" }),
  );
  await user.click(screen.getByRole("button", { name: "Close evidence" }));
  expect(document.activeElement).toBe(
    screen.getAllByRole("button", { name: "View evidence" })[0],
  );
});
it("brings already-open evidence back into focus on repeated View clicks", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  );
  const trigger = screen.getAllByRole("button", { name: "View evidence" })[0];
  await user.click(trigger);
  trigger.focus();
  await user.click(trigger);
  expect(document.activeElement).toBe(
    screen.getByRole("heading", { name: "Weekend bookstore" }),
  );
});
