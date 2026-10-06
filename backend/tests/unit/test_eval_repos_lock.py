import json
import re
from pathlib import Path


LOCKFILE = (
    Path(__file__).resolve().parents[2]
    / "evaluation"
    / "repos.lock"
)


def load_lockfile():
    return json.loads(LOCKFILE.read_text(encoding="utf-8"))


def test_lockfile_has_five_repositories():
    data = load_lockfile()

    assert data["schema_version"] == 1
    assert isinstance(data["repositories"], list)
    assert len(data["repositories"]) == 5


def test_repository_entries_have_valid_structure():
    required_fields = {"name", "url", "commit_sha", "purpose"}

    for repo in load_lockfile()["repositories"]:
        assert set(repo) == required_fields
        assert re.fullmatch(r"[^/\s]+/[^/\s]+", repo["name"])
        assert repo["url"] == f"https://github.com/{repo['name']}"
        assert re.fullmatch(r"[0-9a-f]{40}", repo["commit_sha"])
        assert isinstance(repo["purpose"], str)
        assert repo["purpose"].strip()


def test_repository_entries_are_unique():
    repositories = load_lockfile()["repositories"]

    names = [repo["name"] for repo in repositories]
    urls = [repo["url"] for repo in repositories]

    assert len(names) == len(set(names))
    assert len(urls) == len(set(urls))