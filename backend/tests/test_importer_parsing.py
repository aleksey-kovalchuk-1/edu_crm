import io
import zipfile
from datetime import date, datetime
from pathlib import Path

import openpyxl
import pytest

from app import importer
from app.importer import ImportFileError, interpret_row, parse_date, read_upload, records, suggest_mapping, validate_mapping

FIXTURES = Path(__file__).parent / 'fixtures'
HEADERS = ['Наименование вуза', 'Вендор', 'ИТ-продукт', '№ договора', 'Дата подписания', 'Действует до', 'Статус передачи', 'Менеджер', 'Ответственные от вуза', 'Примечание']


def xlsx_bytes(rows, title='Реестр договоров'):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    if title:
        sheet.append([title])
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def sample_xlsx():
    return xlsx_bytes([
        HEADERS,
        ['Волжский институт цифровых технологий', 'РТК ИТ', 'Учебная среда', 'Д-001', datetime(2026, 1, 15), None, 'Передано', 'Анна  Демо', 'Иван Демо; Мария Демо', ''],
        [None, None, None, None, None, None, None, None, None, None],
        ['Уральская инженерная академия', 'РТК ИТ', 'Тестовый стенд', 1002, '15.03.2026', '2027-03-15', '', '', '', 'Проверка'],
    ])


def test_xlsx_title_row_is_skipped_and_empty_rows_ignored():
    sheet = read_upload('Реестр.XLSX', sample_xlsx())
    assert sheet.header_row == 2
    assert sheet.headers == HEADERS
    assert [row_number for row_number, _ in sheet.rows] == [3, 5]


def test_mapping_is_suggested_from_russian_synonyms():
    mapping = suggest_mapping(HEADERS)
    assert mapping == {
        'university_name': 'Наименование вуза', 'vendor': 'Вендор', 'software': 'ИТ-продукт', 'contract_number': '№ договора',
        'license_signed_at': 'Дата подписания', 'license_valid_until': 'Действует до', 'transfer_status': 'Статус передачи',
        'manager_full_name': 'Менеджер', 'university_contacts': 'Ответственные от вуза', 'comment': 'Примечание', 'it_directions': None,
    }
    assert validate_mapping(HEADERS, mapping) == []


def test_mapping_problems_are_reported():
    problems = validate_mapping(HEADERS, {'university_name': 'Вендор', 'vendor': 'Вендор', 'software': 'Нет такого', 'unknown': 'x'})
    assert any('Неизвестные поля' in problem for problem in problems)
    assert any('Номер договора' in problem for problem in problems)
    assert any('Нет такого' in problem for problem in problems)
    assert any('Один столбец выбран' in problem for problem in problems)


def test_rows_are_interpreted_with_defaults_and_lists():
    sheet = read_upload('reestr.xlsx', sample_xlsx())
    first, second = [interpret_row(number, record) for number, record in records(sheet, suggest_mapping(sheet.headers))]
    assert first.is_valid, first.errors
    assert first.values['license_valid_until'] == date(2027, 1, 15)
    assert first.values['transfer_status'] == 'transferred'
    assert first.values['manager_full_name'] == 'Анна Демо'
    assert first.values['university_contacts'] == ['Иван Демо', 'Мария Демо']
    assert second.is_valid, second.errors
    assert second.values['contract_number'] == '1002'
    assert (second.values['license_signed_at'], second.values['license_valid_until']) == (date(2026, 3, 15), date(2027, 3, 15))
    assert second.values['transfer_status'] == 'not_started'


def test_xls_fixture_is_read_including_date_cells():
    sheet = read_upload('catalog_sample.xls', (FIXTURES / 'catalog_sample.xls').read_bytes())
    assert sheet.header_row == 2
    results = [interpret_row(number, record) for number, record in records(sheet, suggest_mapping(sheet.headers))]
    assert all(result.is_valid for result in results), [result.errors for result in results]
    assert results[0].values['license_signed_at'] == date(2026, 2, 1)
    assert results[0].values['license_valid_until'] == date(2027, 2, 1)
    assert results[0].values['transfer_status'] == 'in_progress'
    assert results[1].values['transfer_status'] == 'transferred'


@pytest.mark.parametrize('record, message', [
    ({'vendor': 'РТК ИТ', 'software': 'Среда', 'contract_number': 'Д', 'license_signed_at': '01.01.2026'}, 'Наименование вуза'),
    ({'university_name': 'Вуз', 'vendor': 'РТК ИТ', 'software': 'Среда', 'contract_number': 'Д', 'license_signed_at': '31.02.2026'}, 'дату подписания'),
    ({'university_name': 'Вуз', 'vendor': 'РТК ИТ', 'software': 'Среда', 'contract_number': 'Д', 'license_signed_at': '01.05.2026', 'license_valid_until': '01.04.2026'}, 'раньше даты подписания'),
    ({'university_name': 'Вуз', 'vendor': 'РТК ИТ', 'software': 'Среда', 'contract_number': 'Д', 'license_signed_at': '01.05.2026', 'transfer_status': 'Потеряно'}, 'Неизвестный статус'),
    ({'university_name': 'В' * 201, 'vendor': 'РТК ИТ', 'software': 'Среда', 'contract_number': 'Д', 'license_signed_at': '01.05.2026'}, 'длиннее 200'),
])
def test_invalid_rows_are_explained(record, message):
    result = interpret_row(7, record)
    assert not result.is_valid
    assert any(message in error for error in result.errors), result.errors


def test_leap_day_validity_and_date_forms():
    assert interpret_row(1, {'university_name': 'Вуз', 'vendor': 'В', 'software': 'П', 'contract_number': 'Д', 'license_signed_at': '29.02.2028'}).values['license_valid_until'] == date(2029, 2, 28)
    assert parse_date(46037) == date(2026, 1, 15)
    assert parse_date('2026-01-15') == date(2026, 1, 15)
    assert parse_date('завтра') is None


@pytest.mark.parametrize('filename, content', [
    ('notes.txt', b'hello'),
    ('reestr.xlsx', b'not a zip file at all'),
    ('reestr.xls', b'PK\x03\x04 but named xls'),
    ('reestr.csv', b'a,b,c'),
])
def test_non_excel_uploads_are_rejected(filename, content):
    with pytest.raises(ImportFileError):
        read_upload(filename, content)


def test_corrupted_xlsx_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('[Content_Types].xml', 'not really a workbook')
    with pytest.raises(ImportFileError):
        read_upload('broken.xlsx', buffer.getvalue())


def test_size_limits(monkeypatch):
    content = sample_xlsx()
    monkeypatch.setattr(importer, 'MAX_FILE_BYTES', len(content) - 1)
    with pytest.raises(ImportFileError, match='10 МБ'):
        read_upload('reestr.xlsx', content)


def test_uncompressed_size_limit_blocks_zip_bombs(monkeypatch):
    monkeypatch.setattr(importer, 'MAX_UNCOMPRESSED_BYTES', 1000)
    with pytest.raises(ImportFileError, match='после распаковки'):
        read_upload('reestr.xlsx', sample_xlsx())


def test_row_limit(monkeypatch):
    monkeypatch.setattr(importer, 'MAX_DATA_ROWS', 1)
    with pytest.raises(ImportFileError, match='строк данных'):
        read_upload('reestr.xlsx', sample_xlsx())


def test_file_without_data_rows_is_rejected():
    with pytest.raises(ImportFileError, match='нет строк'):
        read_upload('reestr.xlsx', xlsx_bytes([HEADERS], title=None))
