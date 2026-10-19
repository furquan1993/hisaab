// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
afterEach(cleanup);
async function expandRow(
  user: ReturnType<typeof userEvent.setup>,
  description: string,
) {
  const row = screen.getByText(description).closest("tr")!;
  await user.click(row);
  return within(row.nextElementSibling as HTMLElement);
}
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
  const details = await expandRow(user, "Credit • purpose unclear");
  await user.click(details.getByRole("button", { name: "Edit entry" }));
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
  const savedDetails = within(saved.nextElementSibling as HTMLElement);
  expect(savedDetails.getByRole("status").textContent).toContain(
    "Assignments saved",
  );
  await waitFor(() =>
    expect(document.activeElement).toBe(within(saved).getByRole("button")),
  );
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
  const details = await expandRow(user, "Credit • purpose unclear");
  await user.click(details.getByRole("button", { name: "Review entry" }));
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
  await waitFor(() =>
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { name: "Statement entries" }),
    ),
  );
  expect(screen.getByRole("status").textContent).toContain("Review saved");
  await user.click(screen.getByRole("tab", { name: "Statement date" }));
  const saved = screen.getByText("Credit • purpose unclear").closest("tr")!;
  expect(within(saved).getByText("refund")).toBeTruthy();
  await user.click(saved);
  await user.click(screen.getByRole("button", { name: "View evidence" }));
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
  const details = await expandRow(user, "Tax • no printed date");
  await user.click(details.getByRole("button", { name: "Review entry" }));
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
  const details = await expandRow(user, "Weekend bookstore");
  await user.click(details.getByRole("button", { name: "View evidence" }));
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
    screen.getByRole("button", { name: "View evidence" }),
  );
});
it("keeps rows compact and opens each action immediately beneath its row", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  );
  expect(screen.queryByRole("button", { name: "View evidence" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Edit entry" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Review entry" })).toBeNull();
  const row = screen.getByText("Weekend bookstore").closest("tr")!;
  const toggle = within(row).getByRole("button", {
    name: "Details for Weekend bookstore",
  });
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  await user.click(row);
  const details = screen.getByRole("region", {
    name: "Details for Weekend bookstore",
  });
  expect(details.closest("tr")?.previousElementSibling).toBe(row);
  expect(toggle.getAttribute("aria-controls")).toBe(details.id);
  await user.click(
    within(details).getByRole("button", { name: "View evidence" }),
  );
  expect(
    within(details).getByRole("complementary", { name: "Source evidence" }),
  ).toBeTruthy();
  await user.click(within(details).getByRole("button", { name: "Edit entry" }));
  expect(
    screen.queryByRole("complementary", { name: "Source evidence" }),
  ).toBeNull();
  expect(
    within(details).getByRole("complementary", { name: "Entry decisions" }),
  ).toBeTruthy();
  await user.selectOptions(screen.getByLabelText("Account"), "");
  expect(toggle.getAttribute("aria-expanded")).toBe("true");
  await user.click(screen.getByRole("button", { name: "Close entry editor" }));
  expect(document.activeElement).toBe(
    within(details).getByRole("button", { name: "Edit entry" }),
  );
  await user.click(
    within(details).getByRole("button", { name: "Review entry" }),
  );
  expect(
    within(details).getByRole("complementary", { name: "Entry review" }),
  ).toBeTruthy();
  await user.type(
    screen.getByLabelText("Review reason"),
    "Draft stays in this row",
  );
  expect(toggle.getAttribute("aria-expanded")).toBe("true");
  await user.click(screen.getByRole("button", { name: "Close review" }));
  expect(document.activeElement).toBe(
    within(details).getByRole("button", { name: "Review entry" }),
  );
  toggle.focus();
  await user.keyboard("{Enter}");
  expect(
    screen.queryByRole("region", { name: "Details for Weekend bookstore" }),
  ).toBeNull();
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  await user.keyboard(" ");
  expect(toggle.getAttribute("aria-expanded")).toBe("true");
  expect(document.activeElement).toBe(toggle);
});
it("opens only one row at a time and resets inline panels when filters change", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  );
  await expandRow(user, "Weekend bookstore");
  const coffees = screen.getAllByText("Corner coffee");
  await user.click(coffees[0].closest("tr")!);
  expect(
    screen.queryByRole("region", { name: "Details for Weekend bookstore" }),
  ).toBeNull();
  const firstCoffee = screen.getByRole("region", {
    name: "Details for Corner coffee",
  });
  await user.click(coffees[1].closest("tr")!);
  expect(
    screen.getByRole("region", { name: "Details for Corner coffee" }).id,
  ).not.toBe(firstCoffee.id);
  await user.click(screen.getByRole("button", { name: "Edit entry" }));
  await user.selectOptions(screen.getByLabelText("Filter dates"), "reviewed");
  expect(
    screen.queryByRole("complementary", { name: "Entry decisions" }),
  ).toBeNull();
  expect(screen.queryByRole("region", { name: /Details for/ })).toBeNull();
  await user.click(screen.getByRole("tab", { name: "Needs review" }));
  const details = await expandRow(user, "Corner coffee • alternate file");
  expect(
    (details.getByRole("button", { name: "Edit entry" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(
    (details.getByRole("button", { name: "Review entry" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  await user.click(details.getByRole("button", { name: "View evidence" }));
  expect(
    screen.getByRole("complementary", { name: "Source evidence" }),
  ).toBeTruthy();
  await user.click(screen.getByRole("tab", { name: "Statement date" }));
  expect(screen.queryByRole("region", { name: /Details for/ })).toBeNull();
  expect(
    screen.queryByRole("complementary", { name: "Source evidence" }),
  ).toBeNull();
});
it("brings already-open evidence back into focus on repeated View clicks", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Explore synthetic demo" }),
  );
  const details = await expandRow(user, "Weekend bookstore");
  const trigger = details.getByRole("button", { name: "View evidence" });
  await user.click(trigger);
  trigger.focus();
  await user.click(trigger);
  expect(document.activeElement).toBe(
    screen.getByRole("heading", { name: "Weekend bookstore" }),
  );
});
