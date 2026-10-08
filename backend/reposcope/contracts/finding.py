from pydantic import BaseModel, ConfigDict, Field


class Finding(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    id: int | None = Field(default=None, gt=0)
    snapshot_id: int = Field(gt=0)
    symbol_id: int | None = Field(default=None, gt=0)
    file_id: int | None = Field(default=None, gt=0)

    category: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)

    score: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
