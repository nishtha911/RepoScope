from .models import User


def test_user_starts_active():
    user = User(id=1, username="Soham", email="soham@example.com")

    assert user.active is True


def test_deactivate_user():
    user = User(id=1, username="Soham", email="soham@example.com")

    user.deactivate()

    assert user.active is False


def test_display_name_strips_whitespace():
    user = User(id=1, username="  Soham  ", email="soham@example.com")

    assert user.display_name() == "Soham"