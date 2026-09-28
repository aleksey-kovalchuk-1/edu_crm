import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'record-backup-run.py'


class BackupRunStatusTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('backup_run', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.status_dir = Path(self.temp.name) / 'status'

    def record(self, **overrides):
        args = dict(status_dir=self.status_dir, trigger='scheduled', label='daily-20260927',
                    started_at='2026-09-27T00:30:00Z', result='success', error=None, now='2026-09-27T00:31:00Z')
        args.update(overrides)
        self.module.record_run(**args)
        return json.loads((self.status_dir / 'last-run.json').read_text())

    def test_writes_only_the_run_fields_next_to_status_json(self):
        (self.status_dir).mkdir(mode=0o700)
        (self.status_dir / 'status.json').write_text('{"generated_at": "x", "backups": []}')
        run = self.record()
        self.assertEqual(run, {'schema': 1, 'trigger': 'scheduled', 'label': 'daily-20260927',
                               'started_at': '2026-09-27T00:30:00Z', 'finished_at': '2026-09-27T00:31:00Z',
                               'result': 'success', 'error': None})
        self.assertEqual((self.status_dir / 'status.json').read_text(), '{"generated_at": "x", "backups": []}')
        # The unprivileged API container must be able to read it, like status.json.
        self.assertEqual(self.status_dir.stat().st_mode & 0o777, 0o755)
        self.assertEqual((self.status_dir / 'last-run.json').stat().st_mode & 0o777, 0o644)

    def test_running_has_no_finish_time_and_failure_keeps_its_stage(self):
        self.assertIsNone(self.record(result='running')['finished_at'])
        failed = self.record(result='failure', error='attachments_backup_failed')
        self.assertEqual((failed['result'], failed['error']), ('failure', 'attachments_backup_failed'))

    def test_rejects_unsafe_values(self):
        with self.assertRaises(ValueError):
            self.record(label='../evil')
        with self.assertRaises(ValueError):
            self.record(error='rm -rf /')
        with self.assertRaises(ValueError):
            self.record(result='maybe')

    def test_replaces_atomically(self):
        self.record()
        self.record(result='failure', error='preflight_failed')
        self.assertEqual(sorted(p.name for p in self.status_dir.iterdir()), ['last-run.json'])


if __name__ == '__main__':
    unittest.main()
