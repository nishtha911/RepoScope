from .config import APP_NAME
from .repository import UserRepository
from .service import UserService


def build_service() -> UserService:
    repository = UserRepository()
    return UserService(repository)


def run_demo() -> dict[str, str | bool]:
    service = build_service()
    user = service.create_user("  Soham  ", " SOHAM@example.com ")

    return {
        "app_name": APP_NAME,
        "username": user.display_name(),
        "email": user.email,
        "active": user.active,
    }


if __name__ == "__main__":
    print(run_demo())