from .exceptions import UserNotFoundError, ValidationError
from .models import User


class UserRepository:
    """Store users in memory for the fixture application."""

    def __init__(self) -> None:
        self._users: dict[int, User] = {}

    def add(self, user: User) -> None:
        if user.id in self._users:
            raise ValidationError(f"User ID {user.id} already exists.")

        self._users[user.id] = user

    def get_by_id(self, user_id: int) -> User:
        if user_id not in self._users:
            raise UserNotFoundError(f"User {user_id} was not found.")

        return self._users[user_id]

    def get_all(self) -> list[User]:
        return list(self._users.values())