from sqlalchemy import update
from sqlalchemy.orm import Session

from core.persistence.models import ImportRecord
from core.statement_balance import parse_hdfc_balance
from tests.persistence_fixture import new_import
from tests.supabase_fixture import SupabaseTests
from tests.test_statement_balance import bill_page


class StatementBalanceHttpTests(SupabaseTests):
    def test_printed_bills_are_selected_owner_scoped_and_read_only(self):
        balance = parse_hdfc_balance(bill_page().page()).to_dict()
        with Session(self.engine) as session, session.begin():
            for records in self.records:
                session.execute(update(ImportRecord).where(ImportRecord.id == records.imported.id).values(printed_balance=balance))
            session.add(new_import(self.records[0], printed_balance=balance))
        for index, records in enumerate(self.records):
            code, bills = self.call("/statement_bills", self.tokens[index])
            self.assertEqual(code, 200)
            self.assertEqual([bill["id"] for bill in bills], [str(records.imported.id)])
            self.assertEqual(bills[0]["printed_balance"]["amount_due"], "5216.00")
        self.assertIn(self.call("/statement_bills")[0], (401, 403))
        self.assertEqual(self.call("/statement_bills", self.tokens[2]), (200, []))
        self.assertIn(self.call("/statement_bills", self.tokens[0], method="PATCH", data={"printed_balance": None})[0], (400, 401, 403, 405))
        self.assertEqual(self.call("/statement_bills", self.tokens[0])[1][0]["printed_balance"]["amount_due"], "5216.00")
