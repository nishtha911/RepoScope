"""Add identifier-aware lexical search to chunks.

Revision ID: d5e2a6b7c801
Revises: c9a1f3e2b845
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d5e2a6b7c801"
down_revision = "c9a1f3e2b845"
branch_labels = None
depends_on = None

UPGRADE_SQL = (
    r"""CREATE FUNCTION reposcope_identifier_text(value text)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
SELECT btrim(lower(regexp_replace(
    regexp_replace(
      regexp_replace(
        regexp_replace(
          regexp_replace(coalesce(value, ''), '([A-Z]+)([A-Z][a-z])', '\1 \2', 'g'),
          '([a-z0-9])([A-Z])', '\1 \2', 'g'),
        '([A-Za-z])([0-9])', '\1 \2', 'g'),
      '([0-9])([A-Za-z])', '\1 \2', 'g'),
    '[^A-Za-z0-9]+', ' ', 'g')))
$function$""",
    r"""CREATE FUNCTION reposcope_refresh_chunk_search()
RETURNS trigger LANGUAGE plpgsql AS $function$
DECLARE symbol_names text;
BEGIN
    SELECT coalesce(s.name, '') || ' ' || coalesce(s.qualname, '')
      INTO symbol_names FROM symbols AS s WHERE s.id = NEW.symbol_id;
    NEW.search_vector :=
        setweight(to_tsvector('pg_catalog.simple'::regconfig,
            reposcope_identifier_text(symbol_names)), 'A')
        || setweight(to_tsvector('pg_catalog.simple'::regconfig,
            reposcope_identifier_text(NEW.text)), 'B');
    RETURN NEW;
END;
$function$""",
    r"""CREATE TRIGGER trg_chunks_search_vector
BEFORE INSERT OR UPDATE OF text, symbol_id, search_vector ON chunks
FOR EACH ROW EXECUTE FUNCTION reposcope_refresh_chunk_search()""",
    r"""CREATE FUNCTION reposcope_refresh_symbol_search()
RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
    UPDATE chunks SET search_vector = NULL WHERE symbol_id = NEW.id;
    RETURN NEW;
END;
$function$""",
    r"""CREATE TRIGGER trg_symbols_search_vector
AFTER UPDATE OF name, qualname ON symbols
FOR EACH ROW EXECUTE FUNCTION reposcope_refresh_symbol_search()""",
    "UPDATE chunks SET search_vector = NULL",
    "CREATE INDEX ix_chunks_search_vector_gin ON chunks USING gin (search_vector)",
)


def upgrade():
    op.add_column(
        "chunks",
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
    )
    for statement in UPGRADE_SQL:
        op.execute(statement)


def downgrade():
    op.execute("DROP TRIGGER trg_symbols_search_vector ON symbols")
    op.execute("DROP TRIGGER trg_chunks_search_vector ON chunks")
    op.execute("DROP FUNCTION reposcope_refresh_symbol_search()")
    op.execute("DROP FUNCTION reposcope_refresh_chunk_search()")
    op.drop_index("ix_chunks_search_vector_gin", table_name="chunks")
    op.drop_column("chunks", "search_vector")
    op.execute("DROP FUNCTION reposcope_identifier_text(text)")
