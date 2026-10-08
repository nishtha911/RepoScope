from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


from reposcope.contracts.vocabulary import RepositoryStatus


class Repository(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        from_attributes=True,
    )

    id: int | None = Field(default=None, gt=0)
    url: HttpUrl
    name: str = Field(min_length=1, pattern=r"^[^/\s]+/[^/\s]+$")
    default_branch: str = Field(default="main", min_length=1)
    status: RepositoryStatus = "pending"
    head_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must contain non-whitespace characters")
        return value
