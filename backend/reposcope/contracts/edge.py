from pydantic import BaseModel, ConfigDict, Field


from reposcope.contracts.vocabulary import EdgeKind


class Edge(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        from_attributes=True,
    )

    id: int | None = Field(default=None, gt=0)
    source_symbol_id: int = Field(gt=0)
    target_symbol_id: int = Field(gt=0)
    kind: EdgeKind
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
