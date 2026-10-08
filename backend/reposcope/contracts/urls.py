import re
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator


def _validate_github_url(value: str, *, pr: bool) -> str:
    value = value.strip()
    if any(char.isspace() for char in value):
        raise ValueError("URL must not contain whitespace")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError("Only HTTPS URLs on github.com are supported")
    if parsed.query or parsed.fragment or "?" in value or "#" in value:
        raise ValueError("URL must not contain a query or fragment")
    pattern = r"/[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+"
    pattern += r"/pull/[1-9][0-9]*/?" if pr else r"/?"
    if not re.fullmatch(pattern, parsed.path):
        raise ValueError("Expected a GitHub pull-request URL" if pr else "Expected a GitHub repository URL")
    repo = parsed.path.split("/")[2]
    if repo in {".", "..", ".git"}:
        raise ValueError("Invalid repository name")
    return value


def validate_repository_url(value: str) -> str:
    return _validate_github_url(value, pr=False)


def validate_pr_url(value: str) -> str:
    return _validate_github_url(value, pr=True)


GitHubRepositoryURL = Annotated[str, AfterValidator(validate_repository_url)]
GitHubPullRequestURL = Annotated[str, AfterValidator(validate_pr_url)]
