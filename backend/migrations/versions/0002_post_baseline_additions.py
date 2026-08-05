"""Bring pre-Alembic databases up to the baseline schema.

Databases created before migrations existed were built by ``create_all`` plus
hand-written ALTERs, so they sit somewhere between revisions. Stamp those at
0001 and run this: every step checks first, so it is a no-op on a database that
0001 just created and a catch-up on an older one.

Revision ID: 0002_post_baseline
Revises: 0001_baseline
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_post_baseline"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


NEW_COLUMNS = [
    ("uploads", "source_files_json", sa.Text()),
    ("uploads", "processing_stage", sa.String(length=64)),
    ("uploads", "processing_error", sa.Text()),
    ("datasets", "mapping_spec_json", sa.Text()),
    ("datasets", "business_classification", sa.String()),
    ("datasets", "dashboard_plan_json", sa.Text()),
    ("datasets", "integration_id", sa.String()),
    ("workspaces", "currency", sa.String(length=3)),
    ("workspaces", "outlook_forecast_dataset_id", sa.String()),
    ("workspaces", "outlook_forecast_date_column", sa.String()),
    ("workspaces", "outlook_forecast_value_column", sa.String()),
    ("users", "billing_provider", sa.String()),
    ("users", "billing_customer_id", sa.String()),
    ("users", "billing_subscription_id", sa.String()),
    # sa.DateTime() renders as TIMESTAMP on Postgres; the old hand-written
    # ALTER used the literal "DATETIME", which Postgres rejects.
    ("users", "subscription_current_period_end", sa.DateTime()),
]

NEW_INDEXES = [
    ("ix_uploads_workspace_id", "uploads", ["workspace_id"]),
    ("ix_datasets_upload_id", "datasets", ["upload_id"]),
    ("ix_datasets_integration_id", "datasets", ["integration_id"]),
    ("ix_analyses_dataset_id", "analyses", ["dataset_id"]),
    ("ix_chat_messages_dataset_id", "chat_messages", ["dataset_id"]),
    ("ix_dashboards_workspace_id", "dashboards", ["workspace_id"]),
    ("ix_workspaces_owner_id", "workspaces", ["owner_id"]),
    ("ix_dataset_relations_workspace_id", "dataset_relations", ["workspace_id"]),
    ("ix_dataset_relations_source_dataset_id", "dataset_relations", ["source_dataset_id"]),
    ("ix_dataset_relations_target_dataset_id", "dataset_relations", ["target_dataset_id"]),
    ("ix_workspace_timeline_snapshots_dataset_id", "workspace_timeline_snapshots", ["dataset_id"]),
]


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    insp = _inspector()
    tables = set(insp.get_table_names())

    if "rate_limit_counters" not in tables:
        op.create_table(
            "rate_limit_counters",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("bucket_key", sa.String(length=255), nullable=False),
            sa.Column("hits", sa.Integer(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("bucket_key", name="uq_rate_limit_counter_bucket"),
        )
        op.create_index(
            "ix_rate_limit_counters_expires_at", "rate_limit_counters", ["expires_at"]
        )
        tables.add("rate_limit_counters")

    for table, column, type_ in NEW_COLUMNS:
        if table not in tables:
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        if column not in existing:
            op.add_column(table, sa.Column(column, type_, nullable=True))

    if "users" in tables:
        op.execute("UPDATE users SET subscription_plan = 'free' WHERE subscription_plan IS NULL")

    insp = _inspector()
    for name, table, columns in NEW_INDEXES:
        if table not in tables:
            continue
        existing = {i["name"] for i in insp.get_indexes(table)}
        if name not in existing:
            op.create_index(name, table, columns)


def downgrade() -> None:
    # Additive and idempotent; dropping the added columns would lose data for
    # no benefit, so only the new table is reversed.
    insp = _inspector()
    if "rate_limit_counters" in set(insp.get_table_names()):
        op.drop_index("ix_rate_limit_counters_expires_at", table_name="rate_limit_counters")
        op.drop_table("rate_limit_counters")
