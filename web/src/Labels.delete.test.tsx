// @vitest-environment jsdom
import { afterEach, beforeAll, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Labels from "./Labels";
import { demoEntries } from "./demo";
import { deleteAccount, previewAccountDeletion } from "./account-deletion";
import type { BrowserClient } from "./client";

beforeAll(() => {
  HTMLDialogElement.prototype.close = function () {
    this.open = false;
  };
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
});
afterEach(cleanup);
const account = {
  id: "pot",
  kind: "account" as const,
  name: "Household",
  version: 1,
  is_archived: false,
};
const preview = { account, entries: [demoEntries[0]], token: "reviewed-token" };
function setup(
  onDelete = vi.fn().mockResolvedValue(undefined),
  onPreviewDelete = vi.fn().mockResolvedValue(preview),
) {
  render(
    <Labels
      kind="account"
      labels={[account]}
      loading={false}
      error=""
      onSave={vi.fn()}
      onReload={vi.fn()}
      onPreviewDelete={onPreviewDelete}
      onDelete={onDelete}
    />,
  );
  return { onDelete, onPreviewDelete, user: userEvent.setup() };
}
it("loads every affected transaction before confirmation and cancellation does not delete", async () => {
  const { user, onDelete, onPreviewDelete } = setup();
  await user.click(screen.getByRole("button", { name: "Delete Household" }));
  expect(onPreviewDelete).toHaveBeenCalledWith(account);
  await screen.findByRole("dialog", { name: "Delete Household?" });
  expect(screen.getByText(demoEntries[0].description)).toBeTruthy();
  expect(onDelete).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(onDelete).not.toHaveBeenCalled();
  expect(document.activeElement).toBe(
    screen.getByRole("button", { name: "Delete Household" }),
  );
});
it("deletes only after confirmation and reports success", async () => {
  const { user, onDelete } = setup();
  await user.click(screen.getByRole("button", { name: "Delete Household" }));
  await user.click(
    await screen.findByRole("button", {
      name: "Delete account and unassign transactions",
    }),
  );
  await waitFor(() => expect(onDelete).toHaveBeenCalledWith(preview));
  expect((await screen.findByRole("status")).textContent).toContain(
    "transactions are now unassigned",
  );
  expect(screen.queryByRole("dialog")).toBeNull();
});
it("cannot confirm an incomplete preview and does not falsely report deletion after failure", async () => {
  const onPreview = vi
    .fn()
    .mockRejectedValueOnce(Error("Could not load transactions"))
    .mockResolvedValue(preview);
  const { user, onDelete } = setup(
    vi.fn().mockRejectedValue(Error("Transactions changed; reopen Delete")),
    onPreview,
  );
  await user.click(screen.getByRole("button", { name: "Delete Household" }));
  expect((await screen.findByRole("alert")).textContent).toContain(
    "Could not load",
  );
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(onDelete).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Delete Household" }));
  await user.click(
    await screen.findByRole("button", {
      name: "Delete account and unassign transactions",
    }),
  );
  expect((await screen.findByRole("alert")).textContent).toContain(
    "Transactions changed",
  );
  expect(
    (
      screen.getByRole("button", {
        name: "Delete account and unassign transactions",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  expect(screen.queryByRole("status")).toBeNull();
});
it("handles empty accounts explicitly", async () => {
  const { user } = setup(
    vi.fn().mockResolvedValue(undefined),
    vi.fn().mockResolvedValue({ ...preview, entries: [] }),
  );
  await user.click(screen.getByRole("button", { name: "Delete Household" }));
  expect(
    await screen.findByText("No transactions are assigned to this account."),
  ).toBeTruthy();
});
it("sends the reviewed token and owner and surfaces conflicts", async () => {
  const rpc = vi.fn().mockResolvedValue({ error: { code: "PT409" } });
  await expect(
    deleteAccount({ rpc } as unknown as BrowserClient, "owner", preview),
  ).rejects.toThrow("Cancel and reopen Delete");
  expect(rpc).toHaveBeenCalledWith("delete_account", {
    p_id: "pot",
    p_expected_token: "reviewed-token",
    p_expected_owner: "owner",
  });
});

it("explains a missing database upgrade instead of suggesting a retry", async () => {
  const rpc = vi
    .fn()
    .mockResolvedValue({ data: null, error: { code: "PGRST202" } });
  await expect(
    previewAccountDeletion({ rpc } as unknown as BrowserClient, "owner", "pot"),
  ).rejects.toThrow("required database update has not been installed");
});
