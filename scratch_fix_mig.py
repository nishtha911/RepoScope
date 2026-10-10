import glob

migration_files = glob.glob('backend/migrations/versions/*_add_pgvector_chunk_table.py')
if not migration_files:
    print("Migration not found")
    exit(1)

f = migration_files[0]
with open(f, 'r', encoding='utf-8') as file:
    content = file.read()

content = content.replace(
    'import sqlalchemy as sa\n',
    'import sqlalchemy as sa\nimport pgvector.sqlalchemy\n'
)

content = content.replace(
    'def upgrade() -> None:\n    """Upgrade schema."""\n',
    'def upgrade() -> None:\n    """Upgrade schema."""\n    op.execute("CREATE EXTENSION IF NOT EXISTS vector")\n'
)

with open(f, 'w', encoding='utf-8') as file:
    file.write(content)
print("Migration fixed.")
