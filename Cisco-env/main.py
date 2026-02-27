from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Annotated
import models
from database import engine, SessionLocal
from sqlalchemy.orm import Session
from sqlalchemy import VARCHAR, TIMESTAMP, Text, Enum

app = FastAPI()


class UserBase(BaseModel):
    id: int
    email: VARCHAR
    pas_hash: VARCHAR

class PostBase(BaseModel):
    id: int
    user_id: int
    created_at: TIMESTAMP
    updated_at: TIMESTAMP
    issue: VARCHAR
    stat: Enum
    notes: Text
    priority: int

def getDB():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(getDB)]

