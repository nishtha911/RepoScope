from functools import wraps


def log_call(func):
    """Print the function name before calling it."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        print(f"Calling {func.__name__}")
        return func(*args, **kwargs)

    return wrapper