import pytest

from .exceptions import UserNotFoundError, ValidationError
from .models import User
from .repository import UserRepository
from .service import UserService


@pytest.fixture
def service():
    return UserService(UserRepository())


def test_create_user(service):
    user = service.create_user("  Soham  ", " SOHAM@example.com ")

    assert user.id == 1
    assert user.username == "Soham"
    assert user.email == "soham@example.com"
    assert service.get_user(user.id) is user


def test_user_ids_increment(service):
    first = service.create_user("Soham", "soham@example.com")
    second = service.create_user("Nishtha", "nishtha@example.com")

    assert first.id == 1
    assert second.id == 2


def test_deactivate_user(service):
    user = service.create_user("Soham", "soham@example.com")

    result = service.deactivate_user(user.id)

    assert result is user
    assert result.active is False


def test_missing_user(service):
    with pytest.raises(UserNotFoundError):
        service.get_user(999)


def test_invalid_input_is_not_stored(service):
    with pytest.raises(ValidationError):
        service.create_user("ab", "soham@example.com")

    assert service.repository.get_all() == []


def test_duplicate_id_is_rejected():
    repository = UserRepository()
    user = User(id=1, username="Soham", email="soham@example.com")
    repository.add(user)

    with pytest.raises(ValidationError):
        repository.add(user)


def test_create_user_logs_call(service, capsys):
    service.create_user("Soham", "soham@example.com")

    assert capsys.readouterr().out == "Calling create_user\n"