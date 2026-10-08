from typing import Literal

SymbolKind = Literal["module", "class", "function", "method", "parameter", "variable", "endpoint"]
EdgeKind = Literal["CALLS", "IMPORTS", "INHERITS", "EXPOSES", "USES", "TESTED_BY"]
RepositoryStatus = Literal["pending", "indexing", "ready", "failed"]
SearchMode = Literal["hybrid", "lexical", "vector"]
Direction = Literal["in", "out"]
FeedbackAction = Literal["accepted", "dismissed", "not_useful"]
