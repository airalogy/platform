"""Add file metadata missing from early stamped source installations.

The initial schema already contains these columns for fresh installations.
Never infer the location of existing objects from a test/default configuration.
"""

import sqlalchemy as sa
from alembic import context, op

revision = "0075_legacy_file_metadata"
down_revision = "0074_analysis_protocol_drafts"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("airalogy_files")}
    backend = None
    if "storage_backend" not in columns:
        backend = context.get_x_argument(as_dictionary=True).get(
            "legacy_storage_backend"
        )
        if backend not in ("oss", "minio"):
            raise RuntimeError(
                "Legacy file tables require an explicit verified storage backend: "
                "alembic -x legacy_storage_backend=oss (or minio) upgrade head. "
                "No objects are copied or moved."
            )
    additions = (
        sa.Column("content_type", sa.String(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column(
            "storage_backend", sa.String(32), nullable=False, server_default=backend
        ),
        sa.Column("storage_namespace", sa.String(256), nullable=True),
        sa.Column("storage_object_key", sa.String(1024), nullable=True),
        sa.Column("external_uri", sa.String(2048), nullable=True),
        sa.Column("storage_metadata", sa.JSON(), nullable=True),
    )
    for column in additions:
        if column.name not in columns:
            op.add_column("airalogy_files", column)
    # Retain the explicitly verified default for old application writers during
    # rollback. Modern writers supply their configured backend explicitly.
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("airalogy_files")}
    if "ix_airalogy_files_project_id" not in indexes:
        op.create_index(
            "ix_airalogy_files_project_id", "airalogy_files", ["project_id"]
        )


def downgrade():
    # These fields belong to the initial schema of supported releases; removing
    # them would destroy file locations and break those releases on rollback.
    pass
