"""Governed analysis-to-Protocol drafts, immutable review and exact version links."""

import sqlalchemy as sa
from alembic import op

revision = "0074_analysis_protocol_drafts"
down_revision = "0073_workflow_project_analysis"
branch_labels = None
depends_on = None
TABLE_NAMES = (
    "analysis_protocol_drafts",
    "analysis_protocol_draft_revisions",
    "analysis_protocol_draft_reviews",
    "analysis_protocol_method_links",
)


def _id(name="id", *, primary_key=False):
    return sa.Column(
        name,
        sa.UUID(),
        nullable=False,
        primary_key=primary_key,
        **({"server_default": sa.func.uuid_generate_v7()} if primary_key else {}),
    )


def _fk(name, table, *, nullable=False, primary_key=False):
    return sa.Column(
        name,
        sa.UUID(),
        sa.ForeignKey(f"{table}.id", ondelete="RESTRICT"),
        nullable=nullable,
        primary_key=primary_key,
    )


def _time(name="created_at"):
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def _digest(name, prefix):
    return (
        sa.Column(name, sa.String(64), nullable=False),
        sa.CheckConstraint(f"{name} ~ '^[0-9a-f]{{64}}$'", name=f"{prefix}_{name}"),
    )


def _revision_fk():
    return sa.ForeignKeyConstraint(
        ["draft_id", "revision"],
        [
            "analysis_protocol_draft_revisions.draft_id",
            "analysis_protocol_draft_revisions.revision",
        ],
        ondelete="RESTRICT",
    )


def upgrade():
    op.create_table(
        TABLE_NAMES[0],
        _id(primary_key=True),
        _fk("project_id", "projects"),
        _fk("method_id", "workflow_analysis_methods"),
        _fk("target_protocol_id", "protocols", nullable=True),
        _fk("base_protocol_version_id", "protocol_versions", nullable=True),
        _fk("created_by_user_id", "users"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state", sa.String(16), nullable=False, server_default="draft"),
        _id("idempotency_key"),
        *_digest("request_digest", "ck_analysis_protocol_draft"),
        _time(),
        _time("updated_at"),
        sa.UniqueConstraint(
            "created_by_user_id",
            "idempotency_key",
            name="uq_analysis_protocol_draft_request",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_analysis_protocol_draft_revision"),
        sa.CheckConstraint(
            "state IN ('draft','reviewed','rejected','applied')",
            name="ck_analysis_protocol_draft_state",
        ),
        sa.CheckConstraint(
            "(target_protocol_id IS NULL) = (base_protocol_version_id IS NULL)",
            name="ck_analysis_protocol_draft_target_pair",
        ),
    )
    op.create_table(
        TABLE_NAMES[1],
        _fk("draft_id", "analysis_protocol_drafts", primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("files", sa.JSON(), nullable=False),
        *(
            item
            for name in (
                "package_digest",
                "manifest_digest",
                "method_digest",
                "request_digest",
            )
            for item in _digest(name, "ck_analysis_protocol_revision")
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        _id("idempotency_key"),
        _fk("created_by_user_id", "users"),
        _time(),
        sa.UniqueConstraint(
            "draft_id", "idempotency_key", name="uq_analysis_protocol_revision_request"
        ),
        sa.CheckConstraint(
            "revision >= 1", name="ck_analysis_protocol_revision_number"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(files::jsonb) = 'object'",
            name="ck_analysis_protocol_revision_files",
        ),
    )
    op.create_table(
        TABLE_NAMES[2],
        _id(primary_key=True),
        _id("draft_id"),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        *_digest("package_digest", "ck_analysis_protocol_review"),
        sa.Column("note", sa.Text(), nullable=False),
        _fk("reviewed_by_user_id", "users"),
        _time(),
        _revision_fk(),
        sa.UniqueConstraint(
            "draft_id", "revision", name="uq_analysis_protocol_review_revision"
        ),
        sa.CheckConstraint(
            "revision >= 1", name="ck_analysis_protocol_review_revision"
        ),
        sa.CheckConstraint(
            "decision IN ('reviewed','rejected')",
            name="ck_analysis_protocol_review_decision",
        ),
    )
    op.create_table(
        TABLE_NAMES[3],
        _fk("protocol_version_id", "protocol_versions", primary_key=True),
        _fk("protocol_id", "protocols"),
        _id("draft_id"),
        sa.Column("revision", sa.Integer(), nullable=False),
        _fk("method_id", "workflow_analysis_methods"),
        *_digest("package_digest", "ck_analysis_protocol_link"),
        _fk("applied_by_user_id", "users"),
        _time(),
        _revision_fk(),
        sa.UniqueConstraint("draft_id", name="uq_analysis_protocol_link_draft"),
        sa.CheckConstraint("revision >= 1", name="ck_analysis_protocol_link_revision"),
    )
    for table, columns in (
        (TABLE_NAMES[0], ("project_id", "method_id")),
        (TABLE_NAMES[3], ("protocol_id", "method_id")),
    ):
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    _create_guards()


def _create_guards():
    op.execute("""
        CREATE FUNCTION reject_analysis_protocol_history_change() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'Analysis Protocol draft history cannot be updated or deleted';
        END; $$ LANGUAGE plpgsql
    """)
    for table in TABLE_NAMES:
        events = "DELETE" if table == TABLE_NAMES[0] else "UPDATE OR DELETE"
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE {events} ON {table} FOR EACH ROW EXECUTE FUNCTION reject_analysis_protocol_history_change()"
        )

    op.execute("""
        CREATE FUNCTION check_analysis_protocol_draft() RETURNS trigger AS $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM workflow_analysis_methods m
            WHERE m.id = NEW.method_id AND m.project_id = NEW.project_id) THEN
            RAISE EXCEPTION 'Analysis Protocol method and draft must belong to the same Project';
          END IF;
          IF NEW.target_protocol_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM protocols p JOIN protocol_versions v ON v.protocol_id = p.id
            WHERE p.id = NEW.target_protocol_id AND p.project_id = NEW.project_id
              AND v.id = NEW.base_protocol_version_id
          ) THEN RAISE EXCEPTION 'Analysis Protocol target and base version must match the draft Project'; END IF;
          IF TG_OP = 'INSERT' THEN
            IF NEW.revision <> 1 OR NEW.state <> 'draft' THEN
              RAISE EXCEPTION 'Analysis Protocol drafts start at draft revision 1';
            END IF;
          ELSE
            IF (to_jsonb(NEW) - ARRAY['revision','state','updated_at'])
              IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['revision','state','updated_at']) THEN
              RAISE EXCEPTION 'Analysis Protocol draft identity is immutable';
            END IF;
            IF OLD.state = 'applied' AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
              RAISE EXCEPTION 'Applied Analysis Protocol drafts are terminal';
            END IF;
            IF NEW.revision <> OLD.revision THEN
              IF NEW.revision <> OLD.revision + 1 OR NEW.state <> 'draft' THEN
                RAISE EXCEPTION 'Analysis Protocol revisions must advance one step into draft';
              END IF;
            ELSIF NEW.state IS DISTINCT FROM OLD.state THEN
              IF NEW.state IN ('reviewed','rejected') AND OLD.state = 'draft' THEN
                IF NOT EXISTS (SELECT 1 FROM analysis_protocol_draft_reviews r
                  WHERE r.draft_id = NEW.id AND r.revision = NEW.revision AND r.decision = NEW.state
                ) THEN RAISE EXCEPTION 'Draft state requires its exact immutable review'; END IF;
              ELSIF NEW.state = 'applied' AND OLD.state = 'reviewed' THEN
                IF NOT EXISTS (SELECT 1 FROM analysis_protocol_method_links l
                  WHERE l.draft_id = NEW.id AND l.revision = NEW.revision AND l.method_id = NEW.method_id
                ) THEN RAISE EXCEPTION 'Applied draft requires its exact Protocol version link'; END IF;
              ELSE RAISE EXCEPTION 'Invalid Analysis Protocol draft state transition'; END IF;
            END IF;
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER check_analysis_protocol_draft BEFORE INSERT OR UPDATE ON analysis_protocol_drafts FOR EACH ROW EXECUTE FUNCTION check_analysis_protocol_draft()"
    )
    op.execute("""
        CREATE FUNCTION check_analysis_protocol_revision() RETURNS trigger AS $$
        DECLARE d analysis_protocol_drafts%ROWTYPE;
        BEGIN
          SELECT * INTO d FROM analysis_protocol_drafts WHERE id = NEW.draft_id FOR UPDATE;
          IF NOT FOUND OR d.state <> 'draft' OR d.revision <> NEW.revision
            OR d.created_by_user_id <> NEW.created_by_user_id THEN
            RAISE EXCEPTION 'Analysis Protocol revision must belong to the current editable draft';
          END IF;
          IF NEW.revision = 1 AND (NEW.idempotency_key <> d.idempotency_key OR NEW.request_digest <> d.request_digest) THEN
            RAISE EXCEPTION 'Initial Analysis Protocol revision must preserve its creation request';
          END IF;
          IF NOT EXISTS (SELECT 1 FROM workflow_analysis_methods WHERE id = d.method_id AND digest = NEW.method_digest) THEN
            RAISE EXCEPTION 'Analysis Protocol revision must preserve the exact published method digest';
          END IF;
          IF jsonb_typeof(NEW.files::jsonb) <> 'object' OR EXISTS (
            SELECT 1 FROM jsonb_each(NEW.files::jsonb) AS entry WHERE jsonb_typeof(entry.value) <> 'string'
          ) THEN RAISE EXCEPTION 'Analysis Protocol files must be a JSON object of text contents'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER check_analysis_protocol_revision BEFORE INSERT ON analysis_protocol_draft_revisions FOR EACH ROW EXECUTE FUNCTION check_analysis_protocol_revision()"
    )
    op.execute("""
        CREATE FUNCTION check_analysis_protocol_review() RETURNS trigger AS $$
        DECLARE d analysis_protocol_drafts%ROWTYPE;
        BEGIN
          SELECT * INTO d FROM analysis_protocol_drafts WHERE id = NEW.draft_id FOR UPDATE;
          IF NOT FOUND OR d.state <> 'draft' OR d.revision <> NEW.revision OR NOT EXISTS (
            SELECT 1 FROM analysis_protocol_draft_revisions r
            WHERE r.draft_id = NEW.draft_id AND r.revision = NEW.revision AND r.package_digest = NEW.package_digest
          ) THEN RAISE EXCEPTION 'Review must match the current draft revision and package'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER check_analysis_protocol_review BEFORE INSERT ON analysis_protocol_draft_reviews FOR EACH ROW EXECUTE FUNCTION check_analysis_protocol_review()"
    )
    op.execute("""
        CREATE FUNCTION check_analysis_protocol_method_link() RETURNS trigger AS $$
        DECLARE d analysis_protocol_drafts%ROWTYPE;
        BEGIN
          SELECT * INTO d FROM analysis_protocol_drafts WHERE id = NEW.draft_id FOR UPDATE;
          IF NOT FOUND OR d.state <> 'reviewed' OR d.revision <> NEW.revision OR d.method_id <> NEW.method_id
            OR (d.target_protocol_id IS NOT NULL AND d.target_protocol_id <> NEW.protocol_id)
            OR NEW.protocol_version_id = d.base_protocol_version_id THEN
            RAISE EXCEPTION 'Protocol link must apply its current reviewed draft to the exact target';
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM analysis_protocol_draft_revisions r
            JOIN analysis_protocol_draft_reviews review ON review.draft_id = r.draft_id AND review.revision = r.revision
            JOIN workflow_analysis_methods m ON m.id = NEW.method_id AND m.digest = r.method_digest AND m.project_id = d.project_id
            JOIN protocols p ON p.id = NEW.protocol_id AND p.project_id = d.project_id
            JOIN protocol_versions v ON v.id = NEW.protocol_version_id AND v.protocol_id = p.id
            WHERE r.draft_id = NEW.draft_id AND r.revision = NEW.revision
              AND r.package_digest = NEW.package_digest AND review.package_digest = NEW.package_digest
              AND review.decision = 'reviewed'
          ) THEN RAISE EXCEPTION 'Protocol link requires exact reviewed revision, package, method and scoped version'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql
    """)
    op.execute(
        "CREATE TRIGGER check_analysis_protocol_method_link BEFORE INSERT ON analysis_protocol_method_links FOR EACH ROW EXECUTE FUNCTION check_analysis_protocol_method_link()"
    )
    op.execute("""
        CREATE FUNCTION check_analysis_protocol_committed_state() RETURNS trigger AS $$
        DECLARE d analysis_protocol_drafts%ROWTYPE; draft_uuid uuid; decision text;
        BEGIN
          IF TG_TABLE_NAME = 'analysis_protocol_drafts' THEN draft_uuid := NEW.id;
          ELSE draft_uuid := NEW.draft_id; END IF;
          SELECT * INTO d FROM analysis_protocol_drafts WHERE id = draft_uuid;
          IF NOT FOUND OR NOT EXISTS (SELECT 1 FROM analysis_protocol_draft_revisions r
            WHERE r.draft_id = d.id AND r.revision = d.revision) THEN
            RAISE EXCEPTION 'Current Analysis Protocol draft revision must exist at commit';
          END IF;
          SELECT r.decision INTO decision FROM analysis_protocol_draft_reviews r
            WHERE r.draft_id = d.id AND r.revision = d.revision;
          IF (d.state = 'draft' AND decision IS NOT NULL)
            OR (d.state IN ('reviewed','rejected') AND decision IS DISTINCT FROM d.state)
            OR (d.state = 'applied' AND decision IS DISTINCT FROM 'reviewed') THEN
            RAISE EXCEPTION 'Analysis Protocol draft state must match its review at commit';
          END IF;
          IF (d.state = 'applied') IS DISTINCT FROM EXISTS (
            SELECT 1 FROM analysis_protocol_method_links l WHERE l.draft_id = d.id
          ) THEN RAISE EXCEPTION 'Analysis Protocol application and version link must commit together'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql
    """)
    for table in TABLE_NAMES:
        op.execute(
            f"CREATE CONSTRAINT TRIGGER complete_{table} AFTER INSERT OR UPDATE ON {table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_analysis_protocol_committed_state()"
        )
    op.execute("""
        CREATE FUNCTION protect_analysis_protocol_target_scope() RETURNS trigger AS $$
        BEGIN
          IF TG_TABLE_NAME = 'protocols' THEN
            IF NEW.project_id IS DISTINCT FROM OLD.project_id AND (
              EXISTS (SELECT 1 FROM analysis_protocol_drafts WHERE target_protocol_id = OLD.id)
              OR EXISTS (SELECT 1 FROM analysis_protocol_method_links WHERE protocol_id = OLD.id)
            ) THEN RAISE EXCEPTION 'Analysis Protocol target Project cannot change'; END IF;
          ELSIF NEW.protocol_id IS DISTINCT FROM OLD.protocol_id AND (
            EXISTS (SELECT 1 FROM analysis_protocol_drafts WHERE base_protocol_version_id = OLD.id)
            OR EXISTS (SELECT 1 FROM analysis_protocol_method_links WHERE protocol_version_id = OLD.id)
          ) THEN RAISE EXCEPTION 'Analysis Protocol target version identity cannot change'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql
    """)
    for table in ("protocols", "protocol_versions"):
        op.execute(
            f"CREATE TRIGGER protect_analysis_protocol_target_scope BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION protect_analysis_protocol_target_scope()"
        )


def downgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text(f"LOCK TABLE {', '.join(TABLE_NAMES)} IN ACCESS EXCLUSIVE MODE")
    )
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM analysis_protocol_drafts)")
    ):
        raise RuntimeError(
            "Cannot downgrade while Analysis Protocol drafts or immutable history exist"
        )
    for table in ("protocols", "protocol_versions"):
        op.execute(f"DROP TRIGGER protect_analysis_protocol_target_scope ON {table}")
    for table in reversed(TABLE_NAMES):
        op.drop_table(table)
    for name in (
        "protect_analysis_protocol_target_scope",
        "check_analysis_protocol_committed_state",
        "check_analysis_protocol_method_link",
        "check_analysis_protocol_review",
        "check_analysis_protocol_revision",
        "check_analysis_protocol_draft",
        "reject_analysis_protocol_history_change",
    ):
        op.execute(f"DROP FUNCTION {name}()")
