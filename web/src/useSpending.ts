import { useEffect, useState } from "react";
import { z } from "zod";
import type { BrowserClient } from "./client";
import type { Entry } from "./domain";
import {
  assignSpendingGroup,
  readSpending,
  spendingGroupSchema,
  type SpendingAssignment,
} from "./spending-client";
import type { SpendingEntry, SpendingGroup } from "./spending-domain";

export function useSpending(
  api: BrowserClient | null,
  ownerId: string | undefined,
  demoRows: Entry[],
  enabled: boolean,
  revision: number,
) {
  const [groups, setGroups] = useState<SpendingGroup[]>([]);
  const [liveRows, setLiveRows] = useState<SpendingEntry[]>([]);
  const [demoAssignments, setDemoAssignments] = useState<SpendingAssignment[]>(
    [],
  );
  const [loading, setLoading] = useState(!!api),
    [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!api || !enabled) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setLiveRows([]);
    // Abort obsolete reads: https://react.dev/reference/react/useEffect#fetching-data-with-effects
    readSpending(api, controller.signal)
      .then((loaded) => {
        if (!controller.signal.aborted) {
          setLiveRows(loaded.rows);
          setGroups(loaded.groups);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setError(
            e instanceof Error
              ? e.message
              : "Could not load spending. Reload to retry.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, enabled, refresh, revision]);
  const rows: SpendingEntry[] = api
    ? liveRows
    : demoRows.map((row) => {
        const assignment = demoAssignments.find(
          (a) => a.entry_id === (row.logical_entry_id ?? row.id),
        );
        return {
          ...row,
          group_id: assignment?.group_id ?? null,
          group_name:
            groups.find((g) => g.id === assignment?.group_id)?.name ?? null,
          group_version: assignment?.version ?? 0,
        };
      });
  async function saveGroup(
    draft: Omit<SpendingGroup, "id"> & { id: string | null },
  ) {
    setBusy(true);
    try {
      let saved: SpendingGroup;
      if (api) {
        if (!ownerId)
          throw Error("Reload your signed-in workspace before saving.");
        const { data, error } = await api.rpc("save_spending_group", {
          p_name: draft.name,
          p_id: draft.id,
          p_expected_version: draft.version,
          p_archived: draft.is_archived,
          p_expected_owner: ownerId,
        });
        if (error)
          throw Error(
            error.code === "PT409"
              ? "This group changed or its name already exists. Reload groups before retrying."
              : "Could not confirm the group save. Reload before retrying.",
          );
        const parsed = spendingGroupSchema.safeParse(data);
        if (!parsed.success)
          throw Error(
            "Could not verify the group save. Reload groups before continuing.",
          );
        saved = parsed.data;
      } else {
        if (
          !draft.name.trim() ||
          draft.name.trim().length > 120 ||
          /[\x00-\x1f\x7f]/.test(draft.name)
        )
          throw Error("Use a group name of 1 to 120 characters.");
        if (
          groups.some(
            (g) =>
              g.id !== draft.id &&
              g.name.toLocaleLowerCase() ===
                draft.name.trim().toLocaleLowerCase(),
          )
        )
          throw Error("This group name already exists.");
        saved = spendingGroupSchema.parse({
          ...draft,
          id: draft.id ?? crypto.randomUUID(),
          name: draft.name.trim(),
          version: draft.version + 1,
        });
      }
      setGroups((current) => [
        ...current.filter((g) => g.id !== saved.id),
        saved,
      ]);
      setLiveRows((current) =>
        current.map((r) =>
          r.group_id === saved.id ? { ...r, group_name: saved.name } : r,
        ),
      );
      return saved;
    } finally {
      setBusy(false);
    }
  }
  async function assign(groupId: string | null, chosen: SpendingEntry[]) {
    if (!chosen.length || chosen.length > 50)
      throw Error("Choose 1 to 50 entries at a time.");
    setBusy(true);
    try {
      let saved: SpendingAssignment[];
      if (api) {
        if (!ownerId)
          throw Error("Reload your signed-in workspace before saving.");
        saved = await assignSpendingGroup(api, ownerId, groupId, chosen);
      } else {
        if (groupId && !groups.some((g) => g.id === groupId && !g.is_archived))
          throw Error("Choose an available group.");
        saved = chosen.map((r) => ({
          entry_id: r.logical_entry_id ?? r.id,
          group_id: groupId,
          version: r.group_version + (r.group_id === groupId ? 0 : 1),
        }));
        setDemoAssignments((current) => [
          ...current.filter(
            (a) => !saved.some((s) => s.entry_id === a.entry_id),
          ),
          ...saved,
        ]);
      }
      setLiveRows((current) =>
        current.map((r) => {
          const assignment = saved.find(
            (a) => a.entry_id === (r.logical_entry_id ?? r.id),
          );
          return assignment
            ? {
                ...r,
                group_id: assignment.group_id,
                group_version: assignment.version,
                group_name:
                  groups.find((g) => g.id === assignment.group_id)?.name ??
                  null,
              }
            : r;
        }),
      );
    } finally {
      setBusy(false);
    }
  }
  return {
    groups,
    rows,
    loading: api ? loading : false,
    error,
    busy,
    saveGroup,
    assign,
    reload: () => setRefresh((n) => n + 1),
  };
}
export type SpendingStore = ReturnType<typeof useSpending>;
