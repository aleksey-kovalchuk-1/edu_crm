"""plan step categories and default-plan flag

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-21

Adds TaskPlanTemplateStep.category (0-4, matching the five board groups already used for
Interactions — see frontend/src/lib/format.ts stageGroups) and TaskPlanTemplate.is_default_plan
(mirrors WorkflowTemplate.is_default), then backfills both for the one template that exists today.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TEMPLATE_NAME = 'Адаптация нового вуза'

# title -> category (0=Первый контакт, 1=Документы, 2=Внедрение, 3=Обучение, 4=Сопровождение)
STEP_CATEGORIES = {
    'Найти ответственного контактного лица в вузе': 0,
    'Уточнить актуальность ИТ-программ': 0,
    'Организовать встречу с представителями вуза': 0,
    'Обменяться необходимыми документами': 1,
    'Доработать документы при необходимости': 1,
    'Подписать документы': 1,
    'Передать учебные материалы, лицензии и документацию': 2,
    'Сопроводить внедрение продукта': 2,
    'Обучить преподавателей вуза': 3,
    'Актуализировать учебную программу': 3,
    'Провести занятия': 3,
    'Обновить документацию и учебные материалы': 4,
    'Организовать повышение квалификации преподавателей': 4,
    'Проконтролировать выполнение этапов': 4,
}


def upgrade() -> None:
    op.add_column('task_plan_template_steps', sa.Column('category', sa.SmallInteger(), nullable=True))
    op.create_check_constraint(op.f('task_plan_template_steps_category_range_check'), 'task_plan_template_steps', 'category >= 0 and category <= 4')
    op.add_column('task_plan_templates', sa.Column('is_default_plan', sa.Boolean(), nullable=False, server_default=sa.false()))

    connection = op.get_bind()
    connection.execute(sa.text(
        'update task_plan_templates set is_default_plan = true where name = :name'
    ), {'name': TEMPLATE_NAME})
    for title, category in STEP_CATEGORIES.items():
        connection.execute(sa.text("""
            update task_plan_template_steps s
            set category = :category
            from task_plan_templates t
            where s.template_id = t.id and t.name = :name and s.title = :title
        """), {'category': category, 'title': title, 'name': TEMPLATE_NAME})


def downgrade() -> None:
    op.drop_column('task_plan_templates', 'is_default_plan')
    op.drop_constraint(op.f('task_plan_template_steps_category_range_check'), 'task_plan_template_steps', type_='check')
    op.drop_column('task_plan_template_steps', 'category')
