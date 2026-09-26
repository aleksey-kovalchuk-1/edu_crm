"""Explicit, resumable document fingerprint backfill; prints counts only."""
import argparse
import base64
from dataclasses import replace
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from .fraud_fingerprint import fingerprint, normalized_record_values, sync_fingerprints
from .models import Learner, LearnerFingerprint
from .security import TokenCipher
from .settings import SettingsError, load_settings


def backfill(db, settings, cipher, *, batch_size=100, after_id=0):
    if not settings.fraud_match_key or cipher is None:
        raise SettingsError('Both FRAUD_MATCH_KEY and LEARNER_DATA_ENCRYPTION_KEY are required for backfill')
    if batch_size <= 0 or after_id < 0:
        raise ValueError('batch_size must be positive and after_id non-negative')
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        settings=replace(settings, fraud_match_coverage_complete=False), learner_cipher=cipher)))
    processed = 0
    last_id = after_id
    while True:
        records = db.scalars(select(Learner).where(Learner.id > last_id).order_by(Learner.id).limit(batch_size)).all()
        if not records:
            break
        for record in records:
            sync_fingerprints(db, record, request)
            last_id = record.id
            processed += 1
        db.commit()
        print(f'Processed {processed} learner records; last_id={last_id}')
    return processed, last_id


def verify_coverage(db, settings, cipher, *, batch_size=100):
    """Recompute every expected digest without writing or printing personal values."""
    if not settings.fraud_match_key or cipher is None:
        raise SettingsError('Both FRAUD_MATCH_KEY and LEARNER_DATA_ENCRYPTION_KEY are required for verification')
    if batch_size <= 0:
        raise ValueError('batch_size must be positive')
    key = base64.urlsafe_b64decode(settings.fraud_match_key)
    counts = {'learners': 0, 'expected': 0, 'missing': 0, 'mismatched': 0, 'unexpected': 0}
    last_id = 0
    while True:
        records = db.scalars(select(Learner).where(Learner.id > last_id).order_by(Learner.id).limit(batch_size)).all()
        if not records:
            return counts
        for record in records:
            counts['learners'] += 1
            actual = {item.kind: item.digest for item in db.scalars(select(LearnerFingerprint).where(
                LearnerFingerprint.learner_id == record.id,
                LearnerFingerprint.key_version == settings.fraud_match_key_version)).all()}
            for kind, value in normalized_record_values(record, cipher).items():
                if value:
                    counts['expected'] += 1
                    expected = fingerprint(kind, value, key)
                    if kind not in actual:
                        counts['missing'] += 1
                    elif actual[kind] != expected:
                        counts['mismatched'] += 1
                elif kind in actual:
                    counts['unexpected'] += 1
            last_id = record.id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-size', type=int, default=100)
    parser.add_argument('--after-id', type=int, default=0)
    parser.add_argument('--verify', action='store_true', help='Check full fingerprint coverage without writing')
    args = parser.parse_args()
    settings = load_settings()
    cipher = TokenCipher(settings.learner_data_encryption_key) if settings.learner_data_encryption_key else None
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with Session(engine) as db:
            if args.verify:
                counts = verify_coverage(db, settings, cipher, batch_size=args.batch_size)
                print('Coverage: ' + ', '.join(f'{name}={value}' for name, value in counts.items()))
                if any(counts[name] for name in ('missing', 'mismatched', 'unexpected')):
                    raise SystemExit(1)
            else:
                backfill(db, settings, cipher, batch_size=args.batch_size, after_id=args.after_id)
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
