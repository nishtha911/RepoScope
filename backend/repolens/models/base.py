from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

 #base is the shared parent of our models, we can make all DBs inherit some property of base class but for now pass rakha hai