"""Echo initial schema.

Revision ID: 0001_echo_initial
Revises:
Create Date: 2026-08-05
"""

from alembic import op

from app.db.postgres import Base
import app.models  # noqa: F401, E402

revision = "0001_echo_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Historical follow-up revisions use inspector guards, so a fresh database
    # can safely create the current schema here without duplicate-table failures.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
