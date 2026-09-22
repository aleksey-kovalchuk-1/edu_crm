"""seed onboarding plan template

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-19

Seeds the one task plan template the spec asks for by name: the university onboarding process,
converted from the existing 14-stage process (docs/design/tasks.md, decision D-174) into actionable
task titles. "Revise documents if necessary" is the one optional step. Offsets are business days from
the plan's start date; each step depends on the previous one. This is permanent baseline data (like
migration 0008's default workflow template), not demo-only seed data — it exists in every environment.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TEMPLATE_NAME = 'Адаптация нового вуза'
TEMPLATE_DESCRIPTION = (
    'Типовой процесс запуска сотрудничества с учебным заведением: от поиска контакта до контроля '
    'выполнения этапов (14 шагов существующего процесса).'
)

# (title, description, start_offset_days, deadline_offset_days, is_optional, approval_required,
#  assignee_rule, checklist_items)
STEPS = [
    ('Найти ответственного контактного лица в вузе', '', 0, 3, False, False, 'university_manager', []),
    ('Уточнить актуальность ИТ-программ', '', 3, 6, False, False, 'university_manager', []),
    ('Организовать встречу с представителями вуза', '', 6, 10, False, False, 'university_manager', []),
    ('Обменяться необходимыми документами', '', 10, 13, False, False, 'university_manager',
     ['Договор', 'Приложения', 'Реквизиты сторон']),
    ('Доработать документы при необходимости', '', 13, 16, True, False, 'university_manager', []),
    ('Подписать документы', '', 16, 19, False, True, 'university_manager', []),
    ('Передать учебные материалы, лицензии и документацию', '', 19, 22, False, False, 'university_manager',
     ['Учебные материалы', 'Лицензии на продукт', 'Документация']),
    ('Сопроводить внедрение продукта', '', 22, 32, False, False, 'university_manager', []),
    ('Обучить преподавателей вуза', '', 32, 37, False, False, 'university_manager',
     ['Программа обучения проведена', 'Материалы переданы преподавателям']),
    ('Актуализировать учебную программу', '', 37, 42, False, False, 'university_manager', []),
    ('Провести занятия', '', 42, 62, False, False, 'university_manager', []),
    ('Обновить документацию и учебные материалы', '', 62, 67, False, False, 'university_manager', []),
    ('Организовать повышение квалификации преподавателей', '', 67, 72, False, False, 'university_manager', []),
    ('Проконтролировать выполнение этапов', '', 72, 74, False, False, 'plan_creator', []),
]


def upgrade() -> None:
    connection = op.get_bind()
    template_id = connection.execute(sa.text(
        'insert into task_plan_templates (name, description, is_active) '
        'values (:name, :description, true) returning id'
    ), {'name': TEMPLATE_NAME, 'description': TEMPLATE_DESCRIPTION}).scalar_one()

    previous_step_id = None
    for position, (title, description, start_offset, deadline_offset, is_optional, approval_required, assignee_rule, checklist) in enumerate(STEPS):
        step_id = connection.execute(sa.text("""
            insert into task_plan_template_steps
                (template_id, position, title, description, assignee_rule, start_offset_days,
                 deadline_offset_days, offset_unit, priority, approval_required, is_optional, depends_on_step_id)
            values
                (:template_id, :position, :title, :description, :assignee_rule, :start_offset,
                 :deadline_offset, 'business', 'normal', :approval_required, :is_optional, :depends_on_step_id)
            returning id
        """), {
            'template_id': template_id, 'position': position, 'title': title, 'description': description,
            'assignee_rule': assignee_rule, 'start_offset': start_offset, 'deadline_offset': deadline_offset,
            'approval_required': approval_required, 'is_optional': is_optional, 'depends_on_step_id': previous_step_id,
        }).scalar_one()
        for item_position, item_title in enumerate(checklist):
            connection.execute(sa.text(
                'insert into task_plan_template_step_checklist_items (step_id, title, position) '
                'values (:step_id, :title, :position)'
            ), {'step_id': step_id, 'title': item_title, 'position': item_position})
        previous_step_id = step_id


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("""
        delete from task_plan_template_step_checklist_items
        where step_id in (
            select s.id from task_plan_template_steps s
            join task_plan_templates t on t.id = s.template_id
            where t.name = :name
        )
    """), {'name': TEMPLATE_NAME})
    connection.execute(sa.text("""
        delete from task_plan_template_steps
        where template_id = (select id from task_plan_templates where name = :name)
    """), {'name': TEMPLATE_NAME})
    connection.execute(sa.text('delete from task_plan_templates where name = :name'), {'name': TEMPLATE_NAME})
