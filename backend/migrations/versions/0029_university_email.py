"""The university's own email address, filled in for the partner roster from the customer's list (2026-09-28).

Revision ID: 0029
Revises: 0028
"""
from alembic import op
import sqlalchemy as sa

revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None

# Kept here rather than imported: a migration must not change when the app's roster does later.
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


def upgrade() -> None:
    op.add_column('universities', sa.Column('email', sa.String(254), nullable=False, server_default=''))
    for name, email in PARTNER_EMAILS.items():
        op.execute(sa.text("update universities set email = :email where name = :name and email = ''")
                   .bindparams(email=email, name=name))


def downgrade() -> None:
    op.drop_column('universities', 'email')
