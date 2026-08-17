"""rename default persona to xiao e

Revision ID: 7f6c1d4a2b90
Revises: 9e98715562bd
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7f6c1d4a2b90"
down_revision: Union[str, None] = "9e98715562bd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE agent_personas
            SET name = '小E',
                system_prompt = replace(system_prompt, '你是「小彗」', '你是「小E」')
            WHERE name = '小彗'
              AND system_prompt LIKE '你是「小彗」，用户的专属 AI 助手%'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE agent_personas
            SET name = '小彗',
                system_prompt = replace(system_prompt, '你是「小E」', '你是「小彗」')
            WHERE name = '小E'
              AND system_prompt LIKE '你是「小E」，用户的专属 AI 助手%'
            """
        )
    )
