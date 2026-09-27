import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'backup_status.py'


class BackupStatusTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('backup_status', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.backups, self.status_dir = root / 'secret-backups', root / 'status'
        self.backups.mkdir()
        self.status_dir.mkdir()

    def file(self, name, size=10):
        (self.backups / name).write_bytes(b'x' * size)

    def write(self, **overrides):
        args = dict(status_dir=self.status_dir, backup_dir=self.backups, trigger='scheduled', label='daily-20260927',
                    started_at='2026-09-27T00:30:00Z', result='success', verified=True, error=None,
                    retention_days=30, min_pairs=7, verification_configured=True, now='2026-09-27T00:31:00Z')
        args.update(overrides)
        self.module.write_status(**args)
        return json.loads((self.status_dir / 'status.json').read_text())

    def test_groups_pairs_newest_first_without_paths(self):
        self.file('edu_crm-20260926T033000Z-daily-20260926.dump.age', 100)
        self.file('attachments-20260926T033001Z-daily-20260926.tar.gz.age', 50)
        self.file('edu_crm-20260927T003000Z-manual-20260927-003000.dump.age', 110)
        self.file('notes.txt')
        status = self.write()
        self.assertEqual([p['label'] for p in status['pairs']], ['manual-20260927-003000', 'daily-20260926'])
        manual, daily = status['pairs']
        self.assertIsNone(manual['attachments'])
        self.assertEqual(daily['database'], {'file': 'edu_crm-20260926T033000Z-daily-20260926.dump.age',
                                             'size_bytes': 100, 'created_at': '2026-09-26T03:30:00Z'})
        text = json.dumps(status)
        self.assertNotIn(str(self.backups), text)
        self.assertNotIn('secret-backups', text)
        self.assertEqual(status['schema'], 1)

    def test_success_sets_last_success_and_failure_keeps_it(self):
        self.assertEqual(self.write()['last_success_at'], '2026-09-27T00:31:00Z')
        failed = self.write(result='failure', error='attachments_backup_failed', verified=None, now='2026-09-28T00:31:00Z')
        self.assertEqual(failed['last_success_at'], '2026-09-27T00:31:00Z')
        self.assertEqual(failed['last_run']['result'], 'failure')
        self.assertEqual(failed['last_run']['error'], 'attachments_backup_failed')

    def test_unknown_backup_folder_keeps_the_previous_list(self):
        self.file('edu_crm-20260926T033000Z-daily-20260926.dump.age')
        self.write()
        failed = self.write(backup_dir='', result='failure', error='preflight_failed', verified=None)
        self.assertEqual([p['label'] for p in failed['pairs']], ['daily-20260926'])

    def test_running_has_no_finish_time(self):
        running = self.write(result='running', verified=None)
        self.assertEqual(running['last_run']['result'], 'running')
        self.assertIsNone(running['last_run']['finished_at'])

    def test_file_is_replaced_atomically_and_readable(self):
        self.write()
        leftovers = [p.name for p in self.status_dir.iterdir() if p.name != 'status.json']
        self.assertEqual(leftovers, [])
        self.assertEqual((self.status_dir / 'status.json').stat().st_mode & 0o777, 0o644)


if __name__ == '__main__':
    unittest.main()
