from .decorators import log_call
from .models import User
from .repository import UserRepository
from .utils import normalize_username, normalize_email
from .validators import validate_username, validate_email


class UserService:
    """Validate user input and coordinate repository operations."""

    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    @log_call
    def create_user(self, username: str, email: str) -> User:
        validate_username(username)
        validate_email(email)

        next_id = max(
            (user.id for user in self.repository.get_all()),
            default=0,
        ) + 1

        user = User(
            id=next_id,
            username=normalize_username(username),
            email=normalize_email(email),
        )

        self.repository.add(user)
        return user

    def get_user(self, user_id: int) -> User:
        return self.repository.get_by_id(user_id)

    def deactivate_user(self, user_id: int) -> User:
        user = self.get_user(user_id)
        user.deactivate()
        return user