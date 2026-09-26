#!/usr/bin/env python3
"""Generate fictional customer-file examples outside the repository."""
import argparse
import json
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.customer_imports import LEARNER_TEMPLATE_HEADERS, VENDOR_TEMPLATE_HEADERS  # noqa: E402


def spreadsheet(path, headers, rows):
    book = openpyxl.Workbook()
    book.active.append(headers)
    for row in rows:
        book.active.append(row)
    book.save(path)


def generate(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = [directory / name for name in ('demo-vendors.xlsx', 'demo-learners.xlsx', 'demo-applications.json')]
    if any(path.exists() for path in paths):
        raise FileExistsError('Демонстрационный файл уже существует; выберите другую папку')
    spreadsheet(paths[0], VENDOR_TEMPLATE_HEADERS,
                [['Демо компания', 'Учебный продукт', 'Тестовый Контакт', '79000000002',
                  'contact@example.test', 'Почта']])
    learner = dict.fromkeys(LEARNER_TEMPLATE_HEADERS, '')
    learner.update({'Фамилия': 'Тестов', 'Имя': 'Иван', 'Номер телефона': 79000000001,
                    'Email': 'learner@example.test', 'Образование': 'Высшее'})
    spreadsheet(paths[1], LEARNER_TEMPLATE_HEADERS, [[learner[header] for header in LEARNER_TEMPLATE_HEADERS]])
    applications = [{'Номер заявки': 'DEMO-1', 'Курс': 'Учебный курс', 'Фамилия': 'Тестов',
                     'Имя': 'Иван', 'Отчество': '', 'Телефон': '79000000001',
                     'Email': 'learner@example.test', 'Номер потока': 'DEMO-P1'}, None]
    paths[2].write_text(json.dumps(applications, ensure_ascii=False, indent=2), encoding='utf-8')
    return paths


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='Папка для трёх демонстрационных файлов')
    for result in generate(parser.parse_args().directory):
        print(result)
