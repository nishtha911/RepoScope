from .config import MIN_USERNAME_LENGTH, MAX_USERNAME_LENGTH
from .exceptions import ValidationError
from .utils import normalize_username, normalize_email


def validate_username(username: str) -> None:
    """Check the length of the normalized username."""
    normalized = normalize_username(username)

    if not MIN_USERNAME_LENGTH <= len(normalized) <= MAX_USERNAME_LENGTH:
        raise ValidationError(
            f"Username must contain {MIN_USERNAME_LENGTH} "
            f"to {MAX_USERNAME_LENGTH} characters."
        )


def validate_email(email: str) -> None:
    """Apply a deliberately simple email check for the fixture."""
    normalized = normalize_email(email)

    if normalized.count("@") != 1:
        raise ValidationError("Email must contain exactly one @.")

    local_part, domain = normalized.split("@")

    if not local_part or not domain or any(
        character.isspace() for character in normalized
    ):
        raise ValidationError("Email must have nonempty parts and no whitespace.")