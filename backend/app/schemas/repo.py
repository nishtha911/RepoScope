from pydantic import BaseModel, ConfigDict, HttpUrl


class RepoCreate(BaseModel):
    full_name: str
    remote_url: HttpUrl
    default_branch: str | None = None


class RepoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    remote_url: str
    default_branch: str | None
    commit_sha: str | None