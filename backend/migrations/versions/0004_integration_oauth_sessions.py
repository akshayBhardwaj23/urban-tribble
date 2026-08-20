"""Move OAuth handoff sessions out of process memory into the database.

The Microsoft connect flow spans two requests: the provider redirects back to
the callback (which stores the issued tokens and the user's file list), and the
user then confirms which workbook to connect. That state lived in a
module-level dict, so with more than one worker the confirmation request could
land on a process that had never seen the session and the connect failed with
"session not found or expired" at random.

Revision ID: 0004_integration_oauth_sessions
Revises: 0003_integration_heartbeat
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_integration_oauth_sessions"
down_revision = "0003_integration_heartbeat"
branch_labels = None
depends_on = None

TABLE = "integration_oauth_sessions"


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    insp = _inspector()
    tables = set(insp.get_table_names())
    if TABLE in tables:
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("user_email", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        # Encrypted envelope: carries the provider's access/refresh tokens.
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_integration_oauth_sessions_workspace_id", TABLE, ["workspace_id"]
    )
    op.create_index("ix_integration_oauth_sessions_expires_at", TABLE, ["expires_at"])


def downgrade() -> None:
    insp = _inspector()
    if TABLE not in set(insp.get_table_names()):
        return
    existing = {i["name"] for i in insp.get_indexes(TABLE)}
    if "ix_integration_oauth_sessions_expires_at" in existing:
        op.drop_index("ix_integration_oauth_sessions_expires_at", table_name=TABLE)
    if "ix_integration_oauth_sessions_workspace_id" in existing:
        op.drop_index("ix_integration_oauth_sessions_workspace_id", table_name=TABLE)
    op.drop_table(TABLE)
