import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / 'record-backup-status.py'


class BackupStatusTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('record_backup_status', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dump = self.root / 'edu_crm-20260927T120000Z-release.dump.age'
        self.archive = self.root / 'attachments-20260927T120001Z-release.tar.gz.age'
        self.status = self.root / 'public' / 'status.json'

    def test_records_only_complete_nonempty_pair_and_no_paths(self):
        self.dump.write_bytes(b'database')
        self.archive.write_bytes(b'attachments')
        self.module.record(self.status, self.dump, self.archive, 'release', verified=False)
        raw = self.status.read_text()
        body = json.loads(raw)
        assert len(body['backups']) == 1
        assert body['backups'][0]['database_bytes'] == 8
        assert body['backups'][0]['attachments_bytes'] == 11
        assert body['backups'][0]['source'] == 'release'
        assert body['backups'][0]['verified'] is False
        assert str(self.root) not in raw and self.dump.name not in raw
        assert os.stat(self.status.parent).st_mode & 0o777 == 0o755
        assert os.stat(self.status).st_mode & 0o777 == 0o644

    def test_missing_or_empty_half_does_not_change_existing_status(self):
        self.dump.write_bytes(b'database')
        self.archive.write_bytes(b'attachments')
        self.module.record(self.status, self.dump, self.archive, 'daily', verified=True)
        before = self.status.read_bytes()
        self.archive.write_bytes(b'')
        with self.assertRaises(ValueError):
            self.module.record(self.status, self.dump, self.archive, 'daily', verified=True)
        assert self.status.read_bytes() == before

    def test_history_is_bounded_and_duplicate_pair_is_replaced(self):
        for index in range(25):
            dump = self.root / f'edu_crm-20260927T1200{index:02d}Z-release-{index}.dump.age'
            archive = self.root / f'attachments-20260927T1200{index:02d}Z-release-{index}.tar.gz.age'
            dump.write_bytes(b'database')
            archive.write_bytes(b'attachments')
            self.module.record(self.status, dump, archive, f'release-{index}', verified=False)
        body = json.loads(self.status.read_text())
        assert len(body['backups']) == 20
        assert body['backups'][0]['source'] == 'release-24'
        self.module.record(self.status, dump, archive, 'release-24', verified=True)
        body = json.loads(self.status.read_text())
        assert len(body['backups']) == 20
        assert body['backups'][0]['verified'] is True

    def test_drops_metadata_when_an_old_pair_was_pruned(self):
        self.dump.write_bytes(b'database')
        self.archive.write_bytes(b'attachments')
        self.module.record(self.status, self.dump, self.archive, 'daily-20260927', verified=True)
        self.dump.unlink()
        new_dump = self.root / 'edu_crm-20260928T120000Z-daily-20260928.dump.age'
        new_archive = self.root / 'attachments-20260928T120001Z-daily-20260928.tar.gz.age'
        new_dump.write_bytes(b'new database')
        new_archive.write_bytes(b'new attachments')
        self.module.record(self.status, new_dump, new_archive, 'daily-20260928', verified=True)
        assert [item['source'] for item in json.loads(self.status.read_text())['backups']] == ['daily-20260928']


if __name__ == '__main__':
    unittest.main()
