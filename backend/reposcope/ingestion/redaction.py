"""Secret redaction for repository content before it is hashed or persisted."""

from __future__ import annotations

import re


_SECRET_PATTERNS = (
    re.compile(
        r"(?i)(\b(?:aws_access_key_id|aws_secret_access_key|api[_-]?key|"
        r"secret|password|token)\b\s*[:=]\s*)(['\"]?)[^\s'\";,]+",
    ),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?"
        r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        re.DOTALL,
    ),
)


def redact_secrets(content: bytes) -> bytes:
    """Replace common credentials in UTF-8 text without changing binary files."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content

    text = _SECRET_PATTERNS[0].sub(r"\1\2[REDACTED]", text)
    text = _SECRET_PATTERNS[1].sub("[REDACTED_GITHUB_TOKEN]", text)
    text = _SECRET_PATTERNS[2].sub("[REDACTED_AWS_ACCESS_KEY]", text)
    text = _SECRET_PATTERNS[3].sub("[REDACTED_PRIVATE_KEY]", text)
    return text.encode("utf-8")