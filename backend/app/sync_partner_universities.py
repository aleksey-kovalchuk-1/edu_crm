"""One-time, repeatable activation of the customer-provided initial university roster.

Historical demo records are deactivated, not renamed or deleted: tasks and interactions
keep their original foreign keys. This is an operator command, not an automatic migration.
"""

import argparse
import json
from dataclasses import dataclass

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from .audit import record_event
from .models import University
from .settings import database_url_from_environment


@dataclass(frozen=True)
class PartnerUniversity:
    name: str
    city: str


# Names are the customer's 2026-09-27 roster. Cities were checked against
# the universities' own contact pages (sources in docs/operations/partner-roster.md).
PARTNERS = (
    PartnerUniversity('МФТИ', 'Долгопрудный'),
    PartnerUniversity('Московский Политех', 'Москва'),
    PartnerUniversity('ИТМО', 'Санкт-Петербург'),
    PartnerUniversity('СПбПУ', 'Санкт-Петербург'),
    PartnerUniversity('СПбГУТ им. проф. М.А. Бонч-Бруевича', 'Санкт-Петербург'),
    PartnerUniversity('Томский политехнический университет', 'Томск'),
    PartnerUniversity('ЮУрГУ (НИУ)', 'Челябинск'),
    PartnerUniversity('РГУ им. А.Н. Косыгина', 'Москва'),
    PartnerUniversity('ВолгГТУ', 'Волгоград'),
    PartnerUniversity('Вятский государственный университет', 'Киров'),
)

# Addresses the customer gave on 2026-09-28; spbu@spbu.ru for СПбПУ was confirmed by the owner the same day.
PARTNER_EMAILS = {
    'ВолгГТУ': 'vstu@vstu.ru',
    'Вятский государственный университет': 'info@vyatsu.ru',
    'ИТМО': 'info@itmo.ru',
    'Московский Политех': 'info@mospolytech.ru',
    'МФТИ': 'mipt@mipt.ru',
    'РГУ им. А.Н. Косыгина': 'info@rguk.ru',
    'СПбГУТ им. проф. М.А. Бонч-Бруевича': 'rector@sut.ru',
    'СПбПУ': 'spbu@spbu.ru',
    'Томский политехнический университет': 'tpu@tpu.ru',
    'ЮУрГУ (НИУ)': 'info@susu.ru',
}

DEMO_NAMES = (
    'Северный технологический университет',
    'Волжский институт цифровых технологий',
    'Уральская инженерная академия',
    'Столичный университет прикладных наук',
    'Сибирский цифровой университет',
    'Южный институт информационных систем',
)


def sync_partner_universities(db: Session, *, apply: bool) -> dict[str, int]:
    universities = db.scalars(select(University).with_for_update()).all()
    by_name = {university.name: university for university in universities}
    partner_names = {item.name for item in PARTNERS}
    demo_names = set(DEMO_NAMES)
    unexpected = sorted(university.name for university in universities
                        if university.is_active and university.name not in partner_names | demo_names)
    if unexpected:
        raise ValueError('unexpected active universities: ' + ', '.join(unexpected))

    created = [item for item in PARTNERS if item.name not in by_name]
    reactivated = [item for item in PARTNERS if item.name in by_name and not by_name[item.name].is_active]
    archived = [university for university in universities
                if university.is_active and university.name in demo_names]
    shared = [item for item in PARTNERS
              if item.name not in by_name or not by_name[item.name].team_visible_to_managers]
    # Only empty addresses are filled: one somebody typed on the card wins.
    unaddressed = [by_name[name] for name in PARTNER_EMAILS if name in by_name and not by_name[name].email]
    result = {'created': len(created), 'reactivated': len(reactivated),
              'archived_demo': len(archived), 'shared_with_managers': len(shared), 'emails_filled': len(unaddressed)}
    if apply and any(result.values()):
        for item in created:
            db.add(University(name=item.name, city=item.city, email=PARTNER_EMAILS.get(item.name, ''),
                              team_visible_to_managers=True))
        for university in unaddressed:
            university.email = PARTNER_EMAILS[university.name]
        for item in reactivated:
            by_name[item.name].is_active = True
        for item in shared:
            if item.name in by_name:
                by_name[item.name].team_visible_to_managers = True
        for university in archived:
            university.is_active = False
            university.team_visible_to_managers = False
        record_event(db, None, None, 'university.roster_sync', entity_type='university',
                     summary='Обновлён начальный список вузов по перечню заказчика', payload=result)
        db.flush()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description='Preview or apply the customer-provided university roster')
    parser.add_argument('--apply', action='store_true', help='commit the change; default is preview')
    args = parser.parse_args()
    engine = create_engine(database_url_from_environment())
    try:
        with Session(engine) as db:
            result = sync_partner_universities(db, apply=args.apply)
            if args.apply:
                db.commit()
            print(json.dumps({'mode': 'applied' if args.apply else 'preview', **result}))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
