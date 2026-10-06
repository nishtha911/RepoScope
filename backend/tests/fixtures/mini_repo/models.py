from dataclasses import dataclass

@dataclass
class User:
    id: int
    username: str
    email: str
    active: bool = True

    def deactivate(self) -> None:
        self.active = False

    def display_name(self) -> str:
        return self.username.strip()