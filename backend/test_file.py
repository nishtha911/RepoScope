from sqlalchemy import select

from repolens.db import SessionLocal
from repolens.models import Repository, File


with SessionLocal() as session:
    repo = session.scalar(
        select(Repository).where(
            Repository.full_name == "demo/example"
        )
    )

    if repo is None:
        raise RuntimeError("Run test_repository.py first")

    file = session.scalar(
        select(File).where(
            File.repository_id == repo.id,
            File.path == "main.py",
        )
    )

    if file is None:
        file = File(
            repository_id=repo.id,
            path="main.py",
            language="python",
        )

        session.add(file)
        session.commit()

        print("File saved")
    else:
        print("File already exists")

    print("File ID:", file.id)
    print("Repository ID:", file.repository_id)
    print("Path:", file.path)
    print("Language:", file.language)