from urllib.parse import urlparse


def validate_repository_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "ssh", "git"} or not parsed.netloc:
        raise ValueError("Repository URL must use https, ssh, or git")
    return url