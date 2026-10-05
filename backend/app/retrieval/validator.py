import re


def validate_citations(answer: str, evidence_ids: set[str]) -> bool:
    cited_ids = set(re.findall(r"\[(E\d+)\]", answer))
    return cited_ids.issubset(evidence_ids)