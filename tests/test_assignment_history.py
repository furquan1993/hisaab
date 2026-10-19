import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from core.assignment_history import read_history


def workbook(path, rows):
    from xml.sax.saxutils import escape
    sheet = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    for index, values in enumerate(rows, 1):
        sheet += f'<row r="{index}">'
        for col, value in enumerate(values):
            sheet += f'<c r="{chr(65+col)}{index}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
        sheet += '</row>'
    sheet += '</sheetData></worksheet>'
    with ZipFile(path, 'w') as z:
        z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Test" r:id="r1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml',sheet)


class HistoryTests(unittest.TestCase):
    def test_layout_changes_signed_credits_and_summary_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'history.xlsx'
            workbook(path, [
                ['Item','Amount','Account'],
                ['Invented shop','100','Home'],
                ['Total','SUM(B2:B2)','Home'],
                ['DATE','Description','AMT','Debit / Credit','Actual Amount','Account','Category'],
                ['2026-01-01','Invented refund','40','Cr','-40','Travel','Transport'],
                ['2026-01-01','Unlabeled','10','','10','',''],
                ['2026-01-01','Invalid','10','','#REF!','Home',''],
            ])
            examples = read_history(path)
            self.assertEqual(len(examples),2)
            self.assertEqual(examples[0].account,'Home')
            self.assertEqual(examples[1].direction,'credit')
            self.assertEqual(examples[1].category,'Transport')
            self.assertEqual(examples,read_history(path))
            self.assertNotEqual(examples[0].source_key,examples[1].source_key)

    def test_preview_never_reads_private_config_or_connects(self):
        from contextlib import redirect_stdout
        from io import StringIO
        import json
        from unittest.mock import patch
        from core.assignment_history import HistoryExample
        from core.cli import main
        examples = [HistoryExample(str(i), 'Invented shop', 'debit', 'Home', None) for i in range(2)]
        output = StringIO()
        with (
            patch('core.assignments.load_examples', return_value=examples),
            patch('core.cli_store.load_config', side_effect=AssertionError('No private config')),
            patch('core.cli_store.create_database_engine', side_effect=AssertionError('No database')),
            redirect_stdout(output),
        ):
            result = main(['assignment-train', '--owner', '00000000-0000-0000-0000-000000000000', 'example.xlsx'])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue()), {'status':'preview', 'examples':2, 'account_patterns':1, 'category_patterns':0})
        self.assertNotIn('Invented shop', output.getvalue())

    def test_duplicate_paths_are_deduplicated_and_escaping_paths_rejected(self):
        from unittest.mock import patch
        from core.assignments import load_examples
        from core.persistence.store import StoreError
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            reference = root/'data/reference'
            reference.mkdir(parents=True)
            path = reference/'history.xlsx'
            workbook(path, [['Item','Amount','Account'], ['Invented shop','100','Home']])
            with patch('core.assignments.CONFIG_ROOT', root):
                self.assertEqual(len(load_examples([path,path])),1)
                outside = root/'outside.xlsx'
                workbook(outside, [['Item','Amount','Account']])
                with self.assertRaises(StoreError):
                    load_examples([outside])
                (reference/'escape.xlsx').symlink_to(outside)
                with self.assertRaises(StoreError):
                    load_examples([reference/'escape.xlsx'])
