import { z } from "zod";
import type { BrowserClient } from "./client";
import { entrySchema } from "./domain";

export const accountDeletionSchema = z.object({
  account: z.object({ id: z.string(), name: z.string(), version: z.number() }),
  entries: z.array(entrySchema),
  token: z.string(),
});
export type AccountDeletion = z.infer<typeof accountDeletionSchema>;

export async function previewAccountDeletion(
  api: BrowserClient,
  ownerId: string | undefined,
  id: string,
): Promise<AccountDeletion> {
  if (!ownerId) throw Error("Reload your signed-in workspace before deleting.");
  const { data, error } = await api.rpc("preview_account_deletion", {
    p_id: id,
    p_expected_owner: ownerId,
  });
  if (error)
    throw Error(
      error.code === "PGRST202" || error.code === "42883"
        ? "Account deletion is not available yet. The required database update has not been installed."
        : "Could not load affected transactions. Reload and try again.",
    );
  return accountDeletionSchema.parse(data);
}

export async function deleteAccount(
  api: BrowserClient,
  ownerId: string | undefined,
  preview: AccountDeletion,
) {
  if (!ownerId) throw Error("Reload your signed-in workspace before deleting.");
  const { data, error } = await api.rpc("delete_account", {
    p_id: preview.account.id,
    p_expected_token: preview.token,
    p_expected_owner: ownerId,
  });
  if (error)
    throw Error(
      error.code === "PT409"
        ? "The account or its transactions changed. Cancel and reopen Delete to review the latest transactions."
        : "Could not confirm deletion. Reload the workspace before trying again.",
    );
  z.object({
    id: z.literal(preview.account.id),
    unassigned_count: z.number().int().nonnegative(),
  }).parse(data);
}
