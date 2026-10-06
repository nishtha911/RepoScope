from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from reposcope.models.base import Base


class Repository(Base):
    __tablename__ = "repositories" #new table called repo

    id: Mapped[int] = mapped_column(primary_key=True) #ID of repo
    full_name: Mapped[str] = mapped_column(String(255), unique=True) #repo name
    remote_url: Mapped[str] = mapped_column(Text) #repo link