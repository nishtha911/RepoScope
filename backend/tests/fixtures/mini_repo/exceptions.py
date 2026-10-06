class MiniRepoError(Exception):
    """Base exception for the fixture application."""


class ValidationError(MiniRepoError):
    """Raised when user input is invalid."""


class UserNotFoundError(MiniRepoError):
    """Raised when a requested user does not exist."""