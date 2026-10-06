from .utils import normalize_username, normalize_email


def test_normalize_username():
    assert normalize_username("  Soham  ") == "Soham"


def test_normalize_email():
    assert normalize_email(" SOHAM@Example.com ") == "soham@example.com"


def test_normalize_empty_username():
    assert normalize_username("   ") == ""