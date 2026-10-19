"""Owner-scoped label and decision writes through real authenticated HTTP."""

from tests.supabase_fixture import SupabaseTests


class DecisionHTTPTests(SupabaseTests):
    def setUp(self):
        with self.engine.begin() as connection:
            for name in (
                "assignment_examples",
                "decision_events",
                "entry_decisions",
                "categories",
                "accounts",
            ):
                connection.exec_driver_sql(
                    "DELETE FROM hisaab." + name + " WHERE owner_id=ANY(%s)",
                    (self.owners,),
                )

    def label(self, kind, name, index=0):
        code, label = self.call(
            "/rpc/save_label",
            self.tokens[index],
            method="POST",
            data={"p_kind": kind, "p_name": name},
        )
        self.assertEqual(code, 200)
        return label

    def test_labels_are_owner_scoped_and_versioned(self):
        category = self.label("category", "Synthetic label")
        account = self.label("account", "Synthetic label")
        self.assertNotEqual(category["id"], account["id"])
        code, rows = self.call("/labels", self.tokens[0])
        self.assertEqual(code, 200)
        self.assertEqual({row["kind"] for row in rows}, {"category", "account"})
        _, foreign = self.call("/labels", self.tokens[1])
        self.assertEqual(foreign, [])
        other = self.label("category", "Synthetic label", 1)
        self.assertNotEqual(other["id"], category["id"])
        code, updated = self.call(
            "/rpc/save_label",
            self.tokens[0],
            method="POST",
            data={
                "p_kind": "account",
                "p_name": "Renamed pot",
                "p_id": account["id"],
                "p_expected_version": 1,
                "p_archived": True,
            },
        )
        self.assertEqual(code, 200)
        self.assertEqual(updated["version"], 2)
        self.assertTrue(updated["is_archived"])
        code, _ = self.call(
            "/rpc/save_label",
            self.tokens[0],
            method="POST",
            data={
                "p_kind": "account",
                "p_name": "Stale name",
                "p_id": account["id"],
                "p_expected_version": 1,
            },
        )
        self.assertEqual(code, 409)

    def test_independent_assignments_persist_without_changing_source_facts(self):
        category = self.label("category", "Synthetic groceries")
        account = self.label("account", "Synthetic household pot")
        entry = str(self.records[0].entry.id)
        code, saved = self.call(
            "/rpc/save_entry_decision",
            self.tokens[0],
            method="POST",
            data={
                "p_entry_id": entry,
                "p_expected_version": 0,
                "p_patch": {"category_id": category["id"], "account_id": account["id"]},
            },
        )
        self.assertEqual(code, 200)
        self.assertEqual(saved["version"], 1)
        code, rows = self.call("/entries?id=eq." + entry, self.tokens[0])
        self.assertEqual(rows[0]["category_name"], "Synthetic groceries")
        self.assertEqual(rows[0]["account_name"], "Synthetic household pot")
        self.assertEqual(rows[0]["amount"], "123.45")
        code, _ = self.call(
            "/rpc/save_entry_decision",
            self.tokens[0],
            method="POST",
            data={
                "p_entry_id": entry,
                "p_expected_version": 1,
                "p_patch": {"category_id": None},
            },
        )
        self.assertEqual(code, 200)
        _, rows = self.call("/entries?id=eq." + entry, self.tokens[0])
        self.assertIsNone(rows[0]["category_id"])
        self.assertEqual(rows[0]["account_id"], account["id"])

    def test_cross_owner_labels_and_stale_versions_cannot_overwrite_work(self):
        foreign = self.label("account", "Synthetic private pot", 1)
        entry = str(self.records[0].entry.id)
        code, _ = self.call(
            "/rpc/save_entry_decision",
            self.tokens[0],
            method="POST",
            data={
                "p_entry_id": entry,
                "p_expected_version": 0,
                "p_patch": {"account_id": foreign["id"]},
            },
        )
        self.assertGreaterEqual(code, 400)
        own = self.label("category", "Synthetic personal category")
        code, _ = self.call(
            "/rpc/save_entry_decision",
            self.tokens[0],
            method="POST",
            data={
                "p_entry_id": entry,
                "p_expected_version": 0,
                "p_patch": {"category_id": own["id"]},
            },
        )
        self.assertEqual(code, 200)
        code, _ = self.call(
            "/rpc/save_entry_decision",
            self.tokens[0],
            method="POST",
            data={
                "p_entry_id": entry,
                "p_expected_version": 0,
                "p_patch": {"category_id": None},
            },
        )
        self.assertEqual(code, 409)

    def test_assignments_are_audited_without_modifying_evidence(self):
        entry = str(self.records[0].entry.id)
        _, before = self.call("/entry_evidence?id=eq." + entry, self.tokens[0])
        account = self.label("account", "Synthetic audited pot")
        code, _ = self.call(
            "/rpc/save_entry_decision",
            self.tokens[0],
            method="POST",
            data={
                "p_entry_id": entry,
                "p_expected_version": 0,
                "p_patch": {"account_id": account["id"]},
            },
        )
        self.assertEqual(code, 200)
        _, after = self.call("/entry_evidence?id=eq." + entry, self.tokens[0])
        self.assertEqual(before, after)
        _, events = self.call("/decision_history?entry_id=eq." + entry, self.tokens[0])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["after"]["account_id"], account["id"])
        self.assertEqual(events[0]["version"], 1)
        _, foreign = self.call("/decision_history?entry_id=eq." + entry, self.tokens[1])
        self.assertEqual(foreign, [])

    def test_archiving_preserves_existing_assignments_but_prevents_new_ones(self):
        entry = str(self.records[0].entry.id)
        account = self.label("account", "Synthetic archived pot")
        code, _ = self.call(
            "/rpc/save_entry_decision",
            self.tokens[0],
            method="POST",
            data={
                "p_entry_id": entry,
                "p_expected_version": 0,
                "p_patch": {"account_id": account["id"]},
            },
        )
        self.assertEqual(code, 200)
        code, _ = self.call(
            "/rpc/save_label",
            self.tokens[0],
            method="POST",
            data={
                "p_kind": "account",
                "p_name": account["name"],
                "p_id": account["id"],
                "p_expected_version": 1,
                "p_archived": True,
            },
        )
        self.assertEqual(code, 200)
        code, _ = self.call(
            "/rpc/save_entry_decision",
            self.tokens[0],
            method="POST",
            data={
                "p_entry_id": entry,
                "p_expected_version": 1,
                "p_patch": {"category_id": None},
            },
        )
        self.assertEqual(code, 200)
        code, _ = self.call(
            "/rpc/save_entry_decision",
            self.tokens[0],
            method="POST",
            data={
                "p_entry_id": entry,
                "p_expected_version": 2,
                "p_patch": {"account_id": None},
            },
        )
        self.assertEqual(code, 200)
        code, _ = self.call(
            "/rpc/save_entry_decision",
            self.tokens[0],
            method="POST",
            data={
                "p_entry_id": entry,
                "p_expected_version": 3,
                "p_patch": {"account_id": account["id"]},
            },
        )
        self.assertEqual(code, 422)

    def test_stale_browser_owner_context_cannot_create_a_label_after_account_switch(
        self,
    ):
        code, _ = self.call(
            "/rpc/save_label",
            self.tokens[1],
            method="POST",
            data={
                "p_kind": "account",
                "p_name": "Synthetic stale private label",
                "p_expected_owner": str(self.owners[0]),
            },
        )
        self.assertEqual(code, 409)
        _, labels = self.call("/labels", self.tokens[1])
        self.assertEqual(labels, [])

    def test_invalid_versions_owner_claims_and_anonymous_writes_are_denied(self):
        code, _ = self.call(
            "/rpc/save_label",
            method="POST",
            data={"p_kind": "account", "p_name": "Synthetic anonymous pot"},
        )
        self.assertGreaterEqual(code, 400)
        code, _ = self.call(
            "/rpc/save_label",
            self.tokens[0],
            method="POST",
            data={
                "p_kind": "account",
                "p_name": "Synthetic null version",
                "p_expected_version": None,
            },
        )
        self.assertEqual(code, 422)
        code, _ = self.call(
            "/rpc/save_entry_decision",
            self.tokens[0],
            method="POST",
            data={
                "p_entry_id": str(self.records[0].entry.id),
                "p_expected_version": 0,
                "p_patch": {"owner_id": str(self.owners[1])},
            },
        )
        self.assertEqual(code, 422)
