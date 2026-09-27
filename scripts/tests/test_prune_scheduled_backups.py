import importlib.util
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / 'prune-scheduled-backups.py'


class ScheduledBackupRetentionTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('retention', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def pair(self, day):
        for name in (f'edu_crm-{day}T033000Z-daily-{day}.dump.age',
                     f'attachments-{day}T033001Z-daily-{day}.tar.gz.age'):
            (self.directory / name).write_bytes(b'encrypted synthetic')

    def test_prunes_only_old_complete_daily_pairs(self):
        for day in ('20260926', '20260925', '20260920', '20260915', '20260910'):
            self.pair(day)
        orphan = self.directory / 'attachments-20260901T033000Z-daily-20260901.tar.gz.age'
        orphan.write_bytes(b'encrypted synthetic')
        manual = self.directory / 'edu_crm-20260901T033000Z-release-20260901.dump.age'
        manual.write_bytes(b'encrypted synthetic')
        removed = self.module.prune_backup_pairs(
            self.directory, retention_days=7, min_pairs=2,
            now=datetime(2026, 9, 27, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(removed, 2)
        self.assertEqual(len(list(self.directory.glob('*daily-20260915*'))), 0)
        self.assertEqual(len(list(self.directory.glob('*daily-20260910*'))), 0)
        self.assertEqual(len(list(self.directory.glob('*daily-20260920*'))), 2)
        self.assertTrue(orphan.exists())
        self.assertTrue(manual.exists())

    def test_preserves_minimum_complete_pairs_even_when_all_old(self):
        for day in ('20260801', '20260802', '20260803'):
            self.pair(day)
        removed = self.module.prune_backup_pairs(
            self.directory, retention_days=7, min_pairs=2,
            now=datetime(2026, 9, 27, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(removed, 1)
        self.assertEqual(len(list(self.directory.glob('*.age'))), 4)


if __name__ == '__main__':
    unittest.main()
