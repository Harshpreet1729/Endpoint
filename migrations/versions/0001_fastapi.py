"""Create EventGate's FastAPI tables."""
from alembic import op
import sqlalchemy as sa

revision = "0001_fastapi"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("eg_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(150), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False))
    op.create_table("eg_endpoints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("eg_users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secret", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("retry_base_delay", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_eg_endpoints_owner_id", "eg_endpoints", ["owner_id"])
    op.create_table("eg_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("endpoint_id", sa.Integer(), sa.ForeignKey("eg_endpoints.id"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("endpoint_id", "event_type", name="uq_eg_subscription"))
    op.create_table("eg_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("eg_users.id"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_eg_event_key"))
    op.create_index("ix_eg_events_owner_id", "eg_events", ["owner_id"])
    op.create_table("eg_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("eg_events.id"), nullable=False),
        sa.Column("endpoint_id", sa.Integer(), sa.ForeignKey("eg_endpoints.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("locked_until", sa.DateTime(), nullable=True))
    op.create_index("ix_eg_deliveries_event_id", "eg_deliveries", ["event_id"])
    op.create_index("ix_eg_deliveries_next_attempt_at", "eg_deliveries", ["next_attempt_at"])
    op.create_table("eg_delivery_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("delivery_id", sa.Integer(), sa.ForeignKey("eg_deliveries.id"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("delivery_id", "attempt_number", name="uq_eg_attempt"))
    op.create_index("ix_eg_delivery_attempts_delivery_id", "eg_delivery_attempts", ["delivery_id"])


def downgrade():
    raise RuntimeError("Automatic data deletion is disabled. Restore a backup to roll back.")
