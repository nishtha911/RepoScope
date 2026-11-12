import importlib.util
from pathlib import Path
import pytest
pytest.importorskip('sqlalchemy')
pytest.importorskip('alembic')
from sqlalchemy import create_engine,text,inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_recommendation_migration_upgrade_and_downgrade():
    path=Path(__file__).resolve().parents[2]/'migrations/versions/d13b7f2a9c40_recommendations.py'
    spec=importlib.util.spec_from_file_location('recommendation_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    assert migration.down_revision and migration.down_revision!='__PARENT__'
    engine=create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE repositories(id INTEGER PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE repository_snapshots(id INTEGER PRIMARY KEY)'))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            tables=inspect(connection).get_table_names()
            assert 'recommendation_runs' in tables and 'recommendation_items' in tables
            assert {'finding','facts','features','evidence'} <= {c['name'] for c in inspect(connection).get_columns('recommendation_items')}
            migration.downgrade()
            assert set(inspect(connection).get_table_names())=={'repositories','repository_snapshots'}
    engine.dispose()
