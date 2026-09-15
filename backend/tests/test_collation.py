from sqlalchemy import create_engine, text

RUSSIAN_COLUMNS = {
    ('universities', 'name'),
    ('universities', 'city'),
    ('universities', 'contact'),
    ('launches', 'program'),
    ('launches', 'product'),
    ('launches', 'owner'),
    ('tasks', 'title'),
    ('tasks', 'owner'),
}


def test_text_columns_use_russian_collation(database_url):
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            rows = connection.execute(text(
                "select table_name, column_name, collation_name from information_schema.columns "
                "where table_schema = 'public'"
            )).all()
    finally:
        engine.dispose()
    collations = {(table, column): collation for table, column, collation in rows}
    assert {key: collations.get(key) for key in RUSSIAN_COLUMNS} == {key: 'ru-RU-x-icu' for key in RUSSIAN_COLUMNS}


def test_names_sort_in_russian_order(database_url):
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            for name in ['Яков', 'ёж', 'Анна', 'елка', 'Жанна']:
                connection.execute(
                    text("insert into universities (name, city, contact) values (:name, 'Москва', '')"),
                    {'name': name},
                )
            ordered = connection.execute(text('select name from universities order by name')).scalars().all()
    finally:
        engine.dispose()
    assert ordered == ['Анна', 'ёж', 'елка', 'Жанна', 'Яков']
