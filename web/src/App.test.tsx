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
it("reviews and rejects a candidate import without replacing published entries", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  );
  await user.click(screen.getByRole("button", { name: "Imports" }));
  await user.click(screen.getByRole("button", { name: "Review candidate" }));
  expect(
    screen.getByRole("heading", { name: "Compare statement sources" }),
  ).toBeTruthy();
  await user.type(
    screen.getByLabelText("Revision reason"),
    "Synthetic candidate is incomplete",
  );
  await user.click(screen.getByRole("button", { name: "Reject candidate" }));
  expect(screen.getByText("rejected")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Statements" }));
  await user.click(screen.getByRole("tab", { name: "Needs review" }));
  expect(screen.queryByText("Corner coffee • alternate file")).toBeNull();
  await user.click(screen.getByRole("tab", { name: "Statement date" }));
  expect(screen.getAllByText("Corner coffee")).toHaveLength(2);
});
it("requires explicit identity and removal review before replacing a source", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  );
  await user.click(screen.getByRole("button", { name: "Imports" }));
  await user.click(screen.getByRole("button", { name: "Review candidate" }));
  await user.click(
    screen.getByRole("button", { name: "Accept reviewed source" }),
  );
  expect(screen.getByRole("alert")).toBeTruthy();
  await user.selectOptions(
    screen.getByRole("combobox", { name: /Identity for candidate row/ }),
    "new",
  );
  await user.click(screen.getByRole("checkbox", { name: /removed rows/ }));
  await user.type(
    screen.getByLabelText("Revision reason"),
    "Synthetic explicitly reviewed replacement",
  );
  await user.click(
    screen.getByRole("button", { name: "Accept reviewed source" }),
  );
  expect(screen.getByText("superseded")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Statements" }));
  expect(screen.getByText("Corner coffee • alternate file")).toBeTruthy();
  expect(screen.queryAllByText("Corner coffee")).toHaveLength(0);
});
it("reviews an unknown entry type without rewriting its original evidence", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  );
  await user.click(screen.getByRole("tab", { name: "Needs review" }));
  const row = screen.getByText("Credit • purpose unclear").closest("tr")!;
  await user.click(within(row).getByRole("button", { name: "Review entry" }));
  await user.selectOptions(
    screen.getByLabelText("Reviewed entry type"),
    "refund",
  );
  await user.type(
    screen.getByLabelText("Review reason"),
    "Synthetic original confirms a refund",
  );
  await user.click(screen.getByRole("button", { name: "Save review" }));
  expect(screen.queryByText("Credit • purpose unclear")).toBeNull();
  await user.click(screen.getByRole("tab", { name: "Statement date" }));
  const saved = screen.getByText("Credit • purpose unclear").closest("tr")!;
  expect(within(saved).getByText("refund")).toBeTruthy();
  await user.click(
    within(saved).getByRole("button", { name: "View evidence" }),
  );
  expect(
    within(
      screen.getByRole("complementary", { name: "Source evidence" }),
    ).getByText("unknown"),
  ).toBeTruthy();
});
it("keeps original date filtering available alongside reviewed dates", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  );
  await user.click(screen.getByRole("tab", { name: "Needs review" }));
  await user.click(
    within(screen.getByText("Tax • no printed date").closest("tr")!).getByRole(
      "button",
      { name: "Review entry" },
    ),
  );
  await user.type(
    screen.getByLabelText("Reviewed transaction date"),
    "2026-01-25",
  );
  await user.type(
    screen.getByLabelText("Review reason"),
    "Synthetic checked the original tax date",
  );
  await user.click(screen.getByRole("button", { name: "Save review" }));
  await user.click(screen.getByRole("tab", { name: "Transaction date" }));
  expect(screen.queryByText("Tax • no printed date")).toBeNull();
  await user.selectOptions(screen.getByLabelText("Filter dates"), "reviewed");
  expect(screen.getByText("Tax • no printed date")).toBeTruthy();
  expect(screen.getByText("2026-01-25")).toBeTruthy();
});
it("reviews statement dates separately while retaining original-date browsing", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  );
  await user.click(screen.getByRole("button", { name: "Imports" }));
  await user.click(
    screen.getAllByRole("button", { name: "Review statement" })[0],
  );
  await user.type(
    screen.getByLabelText("Corrected statement date (optional)"),
    "2026-02-01",
  );
  await user.type(
    screen.getByLabelText("Statement review reason"),
    "Synthetic verified bill date",
  );
  await user.click(
    screen.getByRole("button", { name: "Save statement review" }),
  );
  await user.click(screen.getByRole("button", { name: "Statements" }));
  expect(screen.getByText("Weekend bookstore")).toBeTruthy();
  await user.selectOptions(screen.getByLabelText("Filter dates"), "reviewed");
  expect(screen.queryByText("Weekend bookstore")).toBeNull();
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
