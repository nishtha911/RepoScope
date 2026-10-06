def normalize_username(username: str) -> str:
    """Remove surrounding whitespace from a username."""
    return username.strip()


def normalize_email(email: str) -> str:
    """Normalize an email for this fixture application."""
    return email.strip().lower()