"""add per-user news smtp settings

Revision ID: f38c9a7d12e4
Revises: d21a6f3c8b47
Create Date: 2026-08-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "f38c9a7d12e4"
down_revision: Union[str, None] = "d21a6f3c8b47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("news_subscriptions")}
    additions = (
        ("smtp_provider", sa.String(length=32)),
        ("smtp_username", sa.String(length=255)),
        ("smtp_password_encrypted", sa.String(length=1024)),
        ("smtp_from_name", sa.String(length=128)),
    )
    for name, column_type in additions:
        if name not in columns:
            op.add_column("news_subscriptions", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("news_subscriptions")}
    for name in ("smtp_from_name", "smtp_password_encrypted", "smtp_username", "smtp_provider"):
        if name in columns:
            op.drop_column("news_subscriptions", name)
