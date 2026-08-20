"""add daily news email

Revision ID: c4b8e11a9f20
Revises: 7f6c1d4a2b90
Create Date: 2026-08-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "c4b8e11a9f20"
down_revision: Union[str, None] = "7f6c1d4a2b90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "notify_channels" in tables:
        op.drop_table("notify_channels")
    if "briefing_seen_at" in {c["name"] for c in inspect(bind).get_columns("users")}:
        op.drop_column("users", "briefing_seen_at")
    if "task_id" in {c["name"] for c in inspect(bind).get_columns("research_reports")}:
        op.drop_column("research_reports", "task_id")

    tables = set(inspect(bind).get_table_names())
    if "news_subscriptions" not in tables:
        op.create_table(
            "news_subscriptions",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("topics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", name="uq_news_subscription_user"),
        )
        op.create_index("ix_news_subscriptions_user_id", "news_subscriptions", ["user_id"])
        op.create_index("ix_news_subscriptions_enabled", "news_subscriptions", ["enabled"])
    if "news_deliveries" not in tables:
        op.create_table(
            "news_deliveries",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("subscription_id", sa.UUID(), nullable=True),
            sa.Column("trigger", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("dedupe_key", sa.String(length=96), nullable=True),
            sa.Column("recipient_email", sa.String(length=255), nullable=False),
            sa.Column("subject", sa.String(length=255), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["subscription_id"], ["news_subscriptions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("dedupe_key", name="uq_news_delivery_dedupe"),
        )
        op.create_index("ix_news_deliveries_user_id", "news_deliveries", ["user_id"])
        op.create_index("ix_news_deliveries_status", "news_deliveries", ["status"])
        op.create_index("ix_news_deliveries_created_at", "news_deliveries", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "news_deliveries" in tables:
        op.drop_table("news_deliveries")
    if "news_subscriptions" in tables:
        op.drop_table("news_subscriptions")
    user_columns = {c["name"] for c in inspect(bind).get_columns("users")}
    if "briefing_seen_at" not in user_columns:
        op.add_column("users", sa.Column("briefing_seen_at", sa.DateTime(timezone=True), nullable=True))
    report_columns = {c["name"] for c in inspect(bind).get_columns("research_reports")}
    if "task_id" not in report_columns:
        op.add_column("research_reports", sa.Column("task_id", sa.UUID(), nullable=True))
