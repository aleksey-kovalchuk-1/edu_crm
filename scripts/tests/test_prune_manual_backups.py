import importlib.util
import os
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'prune-manual-backups.py'
DAY = 86400


class ManualBackupCleanupTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('manual_cleanup', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.keep = self.dir / 'keep-manual-backups.txt'
        self.now = time.time()

    def file(self, name, age_days):
        path = self.dir / name
        path.write_bytes(b'encrypted synthetic')
        stamp = self.now - age_days * DAY
        os.utime(path, (stamp, stamp))

    def pair(self, label, age_days, stamp='20260801T100000Z'):
        self.file(f'edu_crm-{stamp}-{label}.dump.age', age_days)
        self.file(f'attachments-{stamp}-{label}.tar.gz.age', age_days)

    def plan(self, **kwargs):
        return self.module.plan_cleanup(self.dir, keep_file=self.keep, older_than_days=30, now=self.now, **kwargs)

    def test_preview_lists_whole_old_manual_pairs_only(self):
        self.pair('manual-20260801-100000', 40)
        self.pair('manual-20260920-100000', 5)            # too recent
        self.pair('daily-20260801', 40)                   # daily copies belong to the daily retention rule
        self.pair('release-20260801', 40)                 # release copies are never cleaned here
        plan = self.plan()
        self.assertEqual([p.label for p in plan.delete], ['manual-20260801-100000'])
        self.assertEqual(sorted(f.name for f in plan.delete[0].files), [
            'attachments-20260801T100000Z-manual-20260801-100000.tar.gz.age',
            'edu_crm-20260801T100000Z-manual-20260801-100000.dump.age'])

    def test_protected_pairs_are_excluded_with_their_reason(self):
        self.pair('manual-20260801-100000', 40)
        self.pair('manual-20260802-100000', 40, stamp='20260802T100000Z')
        self.keep.write_text('# label  reason\nmanual-20260801-100000  выпуск 1.4, откат\n')
        plan = self.plan()
        self.assertEqual([p.label for p in plan.delete], ['manual-20260802-100000'])
        self.assertEqual(plan.protected, {'manual-20260801-100000': 'выпуск 1.4, откат'})

    def test_incomplete_pairs_are_reported_and_never_deleted(self):
        self.file('edu_crm-20260801T100000Z-manual-20260801-100000.dump.age', 40)
        plan = self.plan()
        self.assertEqual(plan.delete, [])
        self.assertEqual([p.label for p in plan.incomplete], ['manual-20260801-100000'])

    def test_a_pair_is_old_only_when_both_files_are_old(self):
        self.file('edu_crm-20260801T100000Z-manual-20260801-100000.dump.age', 40)
        self.file('attachments-20260801T100000Z-manual-20260801-100000.tar.gz.age', 10)
        self.assertEqual(self.plan().delete, [])

    def test_apply_deletes_both_files_of_each_planned_pair_and_nothing_else(self):
        self.pair('manual-20260801-100000', 40)
        self.pair('manual-20260802-100000', 40, stamp='20260802T100000Z')
        self.keep.write_text('manual-20260802-100000 инцидент\n')
        self.file('notes.txt', 400)
        removed = self.module.apply_plan(self.plan())
        self.assertEqual(removed, ['manual-20260801-100000'])
        remaining = sorted(p.name for p in self.dir.iterdir())
        self.assertEqual(remaining, [
            'attachments-20260802T100000Z-manual-20260802-100000.tar.gz.age',
            'edu_crm-20260802T100000Z-manual-20260802-100000.dump.age',
            'keep-manual-backups.txt', 'notes.txt'])

    def test_a_malformed_keep_list_refuses_to_plan(self):
        self.pair('manual-20260801-100000', 40)
        self.keep.write_text('manual-20260801-100000\n')  # no reason given
        with self.assertRaises(ValueError):
            self.plan()

    def test_cli_previews_by_default(self):
        self.pair('manual-20260801-100000', 40)
        code = self.module.main([str(self.dir), '--keep-file', str(self.keep), '--older-than-days', '30'])
        self.assertEqual(code, 0)
        self.assertEqual(len(list(self.dir.glob('*.age'))), 2)  # preview deleted nothing


if __name__ == '__main__':
    unittest.main()
