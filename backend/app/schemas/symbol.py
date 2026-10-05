from pydantic import BaseModel


class SymbolRead(BaseModel):
    id: int
    file_id: int
    name: str
    kind: str
    qualified_name: str | None = None
    start_line: int
    end_line: int