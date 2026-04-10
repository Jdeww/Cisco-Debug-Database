from sqlalchemy import Integer, Text, Column, VARCHAR, TIMESTAMP, Enum, ForeignKey
from database import Base
from sqlalchemy import func

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key = True, index = True)
    email = Column(VARCHAR(255), unique = True, nullable = False)
    pas_hash = Column(VARCHAR(255), nullable = False)
    role = Column(Enum("client", "admin"), nullable = False, server_default = "client")

class Post(Base):
    __tablename__ = 'posts'

    id = Column(Integer, primary_key = True, index = True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable = False)
    created_at = Column(TIMESTAMP, server_default = func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default = func.current_timestamp(), onupdate = func.current_timestamp())
    issue = Column(VARCHAR(360), nullable = False)
    stat = Column(Enum("In review", "Issue resolved", "Issue submitted"), server_default = "Issue submitted", nullable = False)
    notes = Column(Text)
    priority = Column(Integer, server_default = '0', nullable = False)

