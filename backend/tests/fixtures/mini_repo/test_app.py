from .app import build_service, run_demo
from .config import APP_NAME
from .service import UserService


def test_build_service():
    service = build_service()

    assert isinstance(service, UserService)
    assert service.repository.get_all() == []


def test_run_demo():
    result = run_demo()

    assert result == {
        "app_name": APP_NAME,
        "username": "Soham",
        "email": "soham@example.com",
        "active": True,
    }