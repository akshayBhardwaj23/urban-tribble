"""Add a heartbeat column so a crashed sync can be reclaimed.

`find_due_integrations` previously excluded status=`syncing` entirely, so a
row whose sync was interrupted by a process crash or restart was excluded
from the schedule forever, and the UI's "Refresh now" button is disabled
while status is `syncing` -- a dead end with no user-recoverable path.
`syncing_started_at` lets a scheduler distinguish "a sync is actually running"
from "a sync started and the process died", by age.

Revision ID: 0003_integration_heartbeat
Revises: 0002_post_baseline
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_integration_heartbeat"
down_revision = "0002_post_baseline"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    insp = _inspector()
    if "data_source_integrations" not in set(insp.get_table_names()):
        return
    existing = {c["name"] for c in insp.get_columns("data_source_integrations")}
    if "syncing_started_at" not in existing:
        op.add_column(
            "data_source_integrations",
            sa.Column("syncing_started_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    insp = _inspector()
    if "data_source_integrations" not in set(insp.get_table_names()):
        return
    existing = {c["name"] for c in insp.get_columns("data_source_integrations")}
    if "syncing_started_at" in existing:
        op.drop_column("data_source_integrations", "syncing_started_at")
