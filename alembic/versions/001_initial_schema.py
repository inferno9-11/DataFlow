"""001_initial_schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-10-26 03:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. users table
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(128), nullable=False),
        sa.Column("role", sa.String(32), server_default="user", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user', 'admin', 'auditor')", name="ck_user_role"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # 2. records table
    op.create_table(
        "records",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("transaction_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("merchant_name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), server_default="pending", nullable=False),
        sa.Column("risk_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IN ('payment', 'transfer', 'refund', 'withdrawal', 'deposit')",
            name="ck_record_category",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'cleared', 'flagged', 'rejected')", name="ck_record_status"
        ),
        sa.CheckConstraint("risk_score >= 0.0 AND risk_score <= 1.0", name="ck_record_risk_score"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_records_user_idempotency"),
    )
    op.create_index("ix_records_user_id", "records", ["user_id"])
    op.create_index("ix_records_transaction_id", "records", ["transaction_id"])
    op.create_index("ix_records_account_id", "records", ["account_id"])
    op.create_index("ix_records_user_occurred", "records", ["user_id", sa.text("occurred_at DESC")])
    op.create_index("ix_records_user_status", "records", ["user_id", "status"])
    op.create_index("ix_records_user_category", "records", ["user_id", "category"])

    # 3. processing_jobs table
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_type", sa.String(32), server_default="bulk_transaction_ingest", nullable=False
        ),
        sa.Column("status", sa.String(24), server_default="queued", nullable=False),
        sa.Column("total_records", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_records", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_records", sa.Integer(), server_default="0", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_retries", sa.Integer(), server_default="3", nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("payload_records", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'partially_failed', 'failed')",
            name="ck_job_status",
        ),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_jobs_user_idempotency"),
    )
    op.create_index("ix_processing_jobs_user_id", "processing_jobs", ["user_id"])
    op.create_index("ix_jobs_user_status", "processing_jobs", ["user_id", "status"])

    # 4. job_item_errors table
    op.create_table(
        "job_item_errors",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "job_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("processing_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_item_errors_job_id", "job_item_errors", ["job_id"])


def downgrade() -> None:
    op.drop_table("job_item_errors")
    op.drop_table("processing_jobs")
    op.drop_table("records")
    op.drop_table("users")
