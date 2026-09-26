"""Explicit, resumable document fingerprint backfill; prints counts only."""
import argparse
from dataclasses import replace
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from .fraud_fingerprint import sync_fingerprints
from .models import Learner
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-size', type=int, default=100)
    parser.add_argument('--after-id', type=int, default=0)
    args = parser.parse_args()
    settings = load_settings()
    cipher = TokenCipher(settings.learner_data_encryption_key) if settings.learner_data_encryption_key else None
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with Session(engine) as db:
            backfill(db, settings, cipher, batch_size=args.batch_size, after_id=args.after_id)
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
