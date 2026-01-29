"""Initial migration - create all tables

Revision ID: 0001
Revises:
Create Date: 2025-01-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("user", "premium", "admin", name="userrole"),
            nullable=False,
            server_default="user",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_approved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("tg_chat_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "approval_status",
            sa.Enum("pending", "approved", "denied", name="approvalstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("approval_token", sa.String(64), nullable=True),
        sa.Column("approval_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_decided_by", sa.BigInteger(), nullable=True),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("premium_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_tg_chat_id", "users", ["tg_chat_id"])

    # PCs table
    op.create_table(
        "pcs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("stream_key", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pcs_user_id", "pcs", ["user_id"])
    op.create_index("ix_pcs_stream_key", "pcs", ["stream_key"], unique=True)

    # Stream sessions table
    op.create_table(
        "stream_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pc_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("live", "done", "error", name="sessionstatus"),
            nullable=False,
            server_default="live",
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["pc_id"], ["pcs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stream_sessions_pc_id", "stream_sessions", ["pc_id"])

    # Clip jobs table
    op.create_table(
        "clip_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "processing",
                "sent",
                "stored",
                "too_big",
                "failed",
                name="clipstatus",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("result_path", sa.String(500), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["session_id"], ["stream_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index("ix_clip_jobs_status", "clip_jobs", ["status"])

    # Payments table
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="USDT"),
        sa.Column(
            "payment_type",
            sa.Enum("premium", "donation", name="paymenttype"),
            nullable=False,
            server_default="premium",
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "completed", "failed", "refunded", name="paymentstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("telegram_payment_charge_id", sa.String(255), nullable=True),
        sa.Column("provider_payment_charge_id", sa.String(255), nullable=True),
        sa.Column("invoice_payload", sa.String(255), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index(
        "ix_payments_telegram_charge_id",
        "payments",
        ["telegram_payment_charge_id"],
        unique=True,
    )

    # Steam accounts table
    op.create_table(
        "steam_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("max_slots", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("file_content_type", sa.String(100), nullable=True),
        sa.Column("file_data", sa.LargeBinary(), nullable=True),
        sa.Column("file_sha256", sa.String(64), nullable=True),
        sa.Column("file_encrypted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("file_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Steam leases table
    op.create_table(
        "steam_leases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("pc_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "released", "expired", name="leasestatus"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["account_id"], ["steam_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pc_id"], ["pcs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_steam_leases_account_id", "steam_leases", ["account_id"])
    op.create_index("ix_steam_leases_pc_id", "steam_leases", ["pc_id"])
    op.create_index("ix_steam_leases_status", "steam_leases", ["status"])


def downgrade() -> None:
    op.drop_table("steam_leases")
    op.drop_table("steam_accounts")
    op.drop_table("payments")
    op.drop_table("clip_jobs")
    op.drop_table("stream_sessions")
    op.drop_table("pcs")
    op.drop_table("users")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS leasestatus")
    op.execute("DROP TYPE IF EXISTS paymentstatus")
    op.execute("DROP TYPE IF EXISTS paymenttype")
    op.execute("DROP TYPE IF EXISTS clipstatus")
    op.execute("DROP TYPE IF EXISTS sessionstatus")
    op.execute("DROP TYPE IF EXISTS approvalstatus")
    op.execute("DROP TYPE IF EXISTS userrole")
