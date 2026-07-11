"""Initial Airalogy Platform Community schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-16 00:00:00.000000
"""

from typing import Sequence

from alembic import op
from sqlalchemy import text

from migrations.model_registry import import_models

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Freeze the schema owned by this revision. `Base.metadata` is also used by
# Alembic autogeneration and therefore contains models added by later revisions.
# Without an explicit list, a fresh install would create future tables here and
# then fail when their real migration runs.
INITIAL_TABLE_NAMES = (
    "airalogy_files",
    "answers",
    "attachments",
    "chats",
    "embeddings",
    "group_projects",
    "group_users",
    "groups",
    "lab_force_delete_jobs",
    "lab_users",
    "labs",
    "oauth_access_tokens",
    "oauth_authorization_codes",
    "oauth_clients",
    "pinned_items",
    "project_group_protocols",
    "project_group_users",
    "project_groups",
    "project_users",
    "projects",
    "protocol_folder_protocols",
    "protocol_folders",
    "protocol_users",
    "protocol_versions",
    "protocol_workflows",
    "protocols",
    "questions",
    "records",
    "star_folders",
    "stars",
    "upvotes",
    "user_aliases",
    "users",
)


def _initial_tables(metadata):
    return [metadata.tables[name] for name in INITIAL_TABLE_NAMES]


def upgrade() -> None:
    bind = op.get_bind()

    _create_extensions(bind)
    _create_uuid_v7_function(bind)
    _create_chinese_text_search_config(bind)

    import_models()
    from app.models.base import Base

    Base.metadata.create_all(bind=bind, tables=_initial_tables(Base.metadata))

    _create_record_search_document_function(bind)
    _create_expression_indexes(bind)


def downgrade() -> None:
    bind = op.get_bind()

    bind.execute(text("DROP INDEX IF EXISTS public.projects_lab_active_idx;"))
    bind.execute(text("DROP INDEX IF EXISTS public.records_created_active_idx;"))
    bind.execute(text("DROP INDEX IF EXISTS public.records_protocol_created_active_idx;"))
    bind.execute(text("DROP INDEX IF EXISTS public.records_user_created_active_idx;"))
    bind.execute(text("DROP INDEX IF EXISTS public.records_latest_active_idx;"))
    bind.execute(text("DROP INDEX IF EXISTS public.records_search_document_tsv_idx;"))

    import_models()
    from app.models.base import Base

    Base.metadata.drop_all(bind=bind, tables=_initial_tables(Base.metadata))

    bind.execute(text("DROP FUNCTION IF EXISTS public.record_search_document(jsonb, text);"))
    bind.execute(text("DROP FUNCTION IF EXISTS public.uuid_generate_v7();"))
    bind.execute(text("DROP TEXT SEARCH CONFIGURATION IF EXISTS public.chinese_cfg;"))


def _create_extensions(bind) -> None:
    bind.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))
    bind.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    bind.execute(text("CREATE EXTENSION IF NOT EXISTS zhparser;"))


def _create_uuid_v7_function(bind) -> None:
    bind.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION public.uuid_generate_v7()
            RETURNS uuid
            LANGUAGE plpgsql
            VOLATILE
            PARALLEL SAFE
            AS $$
            DECLARE
                unix_ts_ms bigint;
                uuid_bytes bytea;
            BEGIN
                unix_ts_ms := floor(extract(epoch from clock_timestamp()) * 1000)::bigint;
                uuid_bytes := decode(lpad(to_hex(unix_ts_ms), 12, '0'), 'hex')
                    || gen_random_bytes(10);
                uuid_bytes := set_byte(uuid_bytes, 6, (get_byte(uuid_bytes, 6) & 15) | 112);
                uuid_bytes := set_byte(uuid_bytes, 8, (get_byte(uuid_bytes, 8) & 63) | 128);
                RETURN encode(uuid_bytes, 'hex')::uuid;
            END;
            $$;
            """
        )
    )


def _create_chinese_text_search_config(bind) -> None:
    bind.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_ts_config cfg
                    JOIN pg_catalog.pg_namespace ns
                        ON ns.oid = cfg.cfgnamespace
                    WHERE cfg.cfgname = 'chinese_cfg'
                        AND ns.nspname = 'public'
                ) THEN
                    CREATE TEXT SEARCH CONFIGURATION public.chinese_cfg (PARSER = zhparser);
                    ALTER TEXT SEARCH CONFIGURATION public.chinese_cfg
                        ADD MAPPING FOR n,v,a,i,e,l WITH simple;
                END IF;
            END
            $$;
            """
        )
    )


def _create_record_search_document_function(bind) -> None:
    bind.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION public.record_search_document(
                record_data jsonb,
                record_report text
            )
            RETURNS text
            LANGUAGE sql
            IMMUTABLE
            PARALLEL SAFE
            AS $$
            WITH RECURSIVE nodes(value, path) AS (
                SELECT COALESCE(record_data, 'null'::jsonb), ARRAY['root']::text[]
                UNION ALL
                SELECT child.value, nodes.path || child.path_segment
                FROM nodes
                CROSS JOIN LATERAL (
                    SELECT
                        object_entries.value,
                        format('o:%s', object_entries.key) AS path_segment
                    FROM jsonb_each(
                        CASE
                            WHEN jsonb_typeof(nodes.value) = 'object' THEN nodes.value
                            ELSE '{}'::jsonb
                        END
                    ) AS object_entries
                    UNION ALL
                    SELECT
                        array_entries.value,
                        format(
                            'a:%s',
                            lpad((array_entries.ordinality - 1)::text, 12, '0')
                        ) AS path_segment
                    FROM jsonb_array_elements(
                        CASE
                            WHEN jsonb_typeof(nodes.value) = 'array' THEN nodes.value
                            ELSE '[]'::jsonb
                        END
                    ) WITH ORDINALITY AS array_entries(value, ordinality)
                ) AS child
            ),
            scalar_values AS (
                SELECT
                    path,
                    CASE jsonb_typeof(value)
                        WHEN 'string' THEN trim(both '"' FROM value::text)
                        WHEN 'number' THEN value::text
                        WHEN 'boolean' THEN value::text
                        ELSE NULL
                    END AS text_value
                FROM nodes
            )
            SELECT concat_ws(
                ' ',
                COALESCE(
                    (
                        SELECT string_agg(text_value, ' ' ORDER BY path)
                        FROM scalar_values
                        WHERE text_value IS NOT NULL
                            AND text_value <> ''
                    ),
                    ''
                ),
                COALESCE(record_report, '')
            );
            $$;
            """
        )
    )


def _create_expression_indexes(bind) -> None:
    bind.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS records_search_document_tsv_idx
            ON public.records
            USING gin (
                to_tsvector(
                    'english',
                    public.record_search_document(data::jsonb, report)
                )
            )
            WHERE deleted_at IS NULL;
            """
        )
    )
    bind.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS records_latest_active_idx
            ON public.records (id, version DESC)
            WHERE deleted_at IS NULL;
            """
        )
    )
    bind.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS records_user_created_active_idx
            ON public.records (user_id, created_at DESC)
            WHERE deleted_at IS NULL;
            """
        )
    )
    bind.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS records_protocol_created_active_idx
            ON public.records (protocol_id, created_at DESC)
            WHERE deleted_at IS NULL;
            """
        )
    )
    bind.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS records_created_active_idx
            ON public.records (created_at DESC)
            WHERE deleted_at IS NULL;
            """
        )
    )
    bind.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS projects_lab_active_idx
            ON public.projects (lab_id)
            WHERE deleted_at IS NULL;
            """
        )
    )
