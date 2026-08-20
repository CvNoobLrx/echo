"""backfill account emails

Revision ID: d21a6f3c8b47
Revises: c4b8e11a9f20
Create Date: 2026-08-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d21a6f3c8b47"
down_revision: Union[str, None] = "c4b8e11a9f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Legacy registrations stored the submitted email only in username.
    op.execute(
        """
        UPDATE users
        SET email = lower(trim(username))
        WHERE email IS NULL
          AND trim(username) ~* '^[A-Z0-9.!#$%&''*+/=?^_`{|}~-]+@[A-Z0-9-]+(\\.[A-Z0-9-]+)+$'
        """
    )


def downgrade() -> None:
    # Backfilled values are valid account data and must not be erased.
    pass
