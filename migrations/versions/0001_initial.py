"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-04 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column(
            "role",
            sa.Enum("owner", "agent", "client", name="userrole", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column(
            "language",
            sa.Enum("ru", "en", "it", name="language", native_enum=False, length=8),
            nullable=True,
        ),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("work_start", sa.Time(), nullable=True),
        sa.Column("work_end", sa.Time(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agents_is_active", "agents", ["is_active"])

    op.create_table(
        "properties",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False, unique=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "property_type",
            sa.Enum(
                "apartment", "studio", "room", "house", name="propertytype", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "available",
                "reserved",
                "rented",
                "archived",
                name="propertystatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("city", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("district", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("address", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("rooms", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("area_m2", sa.Numeric(8, 2), nullable=True),
        sa.Column("floor", sa.Integer(), nullable=True),
        sa.Column("price_month", sa.Numeric(10, 2), nullable=False),
        sa.Column("deposit", sa.Numeric(10, 2), nullable=True),
        sa.Column("min_term_months", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_term_months", sa.Integer(), nullable=True),
        sa.Column("available_from", sa.Date(), nullable=True),
        sa.Column("furnished", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("pets_allowed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("utilities_included", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("features", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("photos", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_properties_status", "properties", ["status"])
    op.create_index("ix_properties_district", "properties", ["district"])
    op.create_index("ix_properties_search", "properties", ["status", "district", "price_month"])

    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "property_id", sa.Integer(), sa.ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "scheduled",
                "completed",
                "cancelled",
                "no_show",
                name="bookingstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("cancel_reason", sa.String(length=255), nullable=True),
        sa.Column("reminder_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("extended_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reschedule_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("ends_at > starts_at", name="ck_bookings_valid_period"),
        postgresql.ExcludeConstraint(
            (sa.column("agent_id"), "="),
            (sa.func.tstzrange(sa.column("starts_at"), sa.column("ends_at")), "&&"),
            name="ex_bookings_agent_no_overlap",
            using="gist",
            where=sa.text("status = 'scheduled'"),
        ),
    )
    op.create_index("ix_bookings_property_id", "bookings", ["property_id"])
    op.create_index("ix_bookings_client_id", "bookings", ["client_id"])
    op.create_index("ix_bookings_agent_id", "bookings", ["agent_id"])
    op.create_index("ix_bookings_status_starts_at", "bookings", ["status", "starts_at"])

    op.create_table(
        "waitlist_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "property_id", sa.Integer(), sa.ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("preferred_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "waiting",
                "offered",
                "booked",
                "cancelled",
                name="waitliststatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_waitlist_entries_client_id", "waitlist_entries", ["client_id"])
    op.create_index(
        "ix_waitlist_property_status", "waitlist_entries", ["property_id", "status", "created_at"]
    )

    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "category",
            sa.Enum(
                "general",
                "booking",
                "property",
                "contract",
                "payment",
                "complaint",
                "other",
                name="ticketcategory",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum("low", "normal", "high", name="ticketpriority", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("open", "in_progress", "resolved", name="ticketstatus", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tickets_client_id", "tickets", ["client_id"])
    op.create_index("ix_tickets_assignee_id", "tickets", ["assignee_id"])
    op.create_index("ix_tickets_status", "tickets", ["status"])

    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "qualified",
                "viewing",
                "negotiation",
                "won",
                "lost",
                name="leadstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("criteria", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="telegram"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_leads_status", "leads", ["status"])

    op.create_table(
        "faq_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "language",
            sa.Enum("ru", "en", "it", name="language", native_enum=False, length=8),
            nullable=False,
        ),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_faq_entries_language", "faq_entries", ["language"])

    op.create_table(
        "excel_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "direction",
            sa.Enum("import", "export", name="syncdirection", native_enum=False, length=8),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_mtime", sa.Float(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("stats", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_excel_sync_runs_direction", "excel_sync_runs", ["direction"])


def downgrade() -> None:
    op.drop_table("excel_sync_runs")
    op.drop_table("faq_entries")
    op.drop_table("leads")
    op.drop_table("tickets")
    op.drop_table("waitlist_entries")
    op.drop_table("bookings")
    op.drop_table("properties")
    op.drop_table("agents")
    op.drop_table("users")
