from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    vk_id = Column(String, index=True, nullable=True)  # id пользователя из ВК
    name = Column(String)
    birth_date = Column(String)   # "1990-05-15"
    birth_time = Column(String)   # "14:30"
    birth_place = Column(String)  # "Москва"

    # Связь: у одного пользователя много "родственников"
    relatives = relationship("Relative", back_populates="owner")

class Relative(Base):
    __tablename__ = "relatives"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))  # чей это друг
    name = Column(String)
    birth_date = Column(String)
    birth_time = Column(String)
    birth_place = Column(String)
    relation_type = Column(String)  # "друг" / "партнёр" / "родственник"

    owner = relationship("User", back_populates="relatives")
