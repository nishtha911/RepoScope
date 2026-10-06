import pytest

from .exceptions import ValidationError
from .validators import validate_username, validate_email


@pytest.mark.parametrize("username", ["abc", "Soham", "a" * 30])
def test_valid_username(username):
    assert validate_username(username) is None


@pytest.mark.parametrize("username", ["", "ab", "a" * 31, "   "])
def test_invalid_username(username):
    with pytest.raises(ValidationError):
        validate_username(username)


@pytest.mark.parametrize(
    "email",
    ["soham@example.com", " USER@Example.com "],
)
def test_valid_email(email):
    assert validate_email(email) is None


@pytest.mark.parametrize(
    "email",
    ["", "invalid", "@example.com", "user@", "a@@b.com", "a b@example.com"],
)
def test_invalid_email(email):
    with pytest.raises(ValidationError):
        validate_email(email)