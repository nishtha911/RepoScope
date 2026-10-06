import sys
from pathlib import Path

# Add the 'backend' directory to sys.path
backend_dir = Path(__file__).resolve().parents[2]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
from sqlalchemy import select

from repolens.db import SessionLocal
from repolens.models import Repository


with SessionLocal() as session:
    repo = session.scalar(
        select(Repository).where(
            Repository.full_name == "demo/example"
        )
    )

    if repo is None:
        repo = Repository(
            full_name="demo/example",
            remote_url="https://github.com/demo/example.git",
        )

        session.add(repo)
        session.commit()

        print("Repository saved")
    else:
        print("Repository already exists")

    print("ID:", repo.id)
    print("Name:", repo.full_name)
    print("URL:", repo.remote_url)