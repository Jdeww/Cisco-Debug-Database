from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Annotated, Optional
import models
from database import engine, SessionLocal
from sqlalchemy.orm import Session
from auth import create_access_token, create_refresh_token, verify_token, SECRET_KEY, ALGORITHM
import jwt

app = FastAPI(title="Cisco Debug Database API")
models.Base.metadata.create_all(bind=engine)


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str


class PostCreate(BaseModel):
    issue: str
    stat: str = "Issue submitted"
    notes: Optional[str] = None
    priority: int = 0


class PostUpdate(BaseModel):
    issue: str
    stat: str
    notes: Optional[str] = None
    priority: int = 0


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dep = Annotated[Session, Depends(get_db)]
token_dep = Annotated[dict, Depends(verify_token)]


# --- Auth ---

@app.post("/auth/login")
async def login(req: LoginRequest, db: db_dep):
    user = db.query(models.User).filter(models.User.email == req.email).first()
    if not user or user.pas_hash != req.password:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {
        "access_token": create_access_token(user.id, user.role),
        "refresh_token": create_refresh_token(user.id, user.role),
        "token_type": "bearer",
        "user_id": user.id,
        "role": user.role,
        "email": user.email,
    }


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: db_dep):
    if req.role not in ("client", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    if db.query(models.User).filter(models.User.email == req.email).first():
        raise HTTPException(status_code=409, detail="An account with that email already exists.")
    user = models.User(email=req.email, pas_hash=req.password, role=req.role)
    db.add(user)
    db.commit()
    return {"message": "User registered successfully"}


@app.post("/auth/refresh")
async def refresh(req: RefreshRequest, db: db_dep):
    try:
        payload = jwt.decode(req.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise jwt.PyJWTError("Wrong token type")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = db.query(models.User).filter(models.User.id == int(payload["sub"])).first()
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")

    return {
        "access_token": create_access_token(user.id, user.role),
        "refresh_token": create_refresh_token(user.id, user.role),
        "token_type": "bearer",
    }


# --- Users ---

@app.get("/users/")
async def list_users(db: db_dep, token: token_dep):
    if token.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return [{"id": u.id, "email": u.email, "role": u.role} for u in db.query(models.User).all()]


@app.get("/users/{user_id}")
async def get_user(user_id: int, db: db_dep, _token: token_dep):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user.id, "email": user.email, "role": user.role}


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: db_dep, token: token_dep):
    if token.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if db.query(models.Post).filter(models.Post.user_id == user_id).first():
        raise HTTPException(status_code=409, detail="Cannot delete user with existing posts.")
    db.delete(user)
    db.commit()


# --- Posts ---

@app.get("/posts/")
async def get_posts(db: db_dep, _token: token_dep):
    return db.query(models.Post).all()


@app.get("/users/{user_id}/posts")
async def get_posts_by_user(user_id: int, db: db_dep, _token: token_dep):
    if not db.query(models.User).filter(models.User.id == user_id).first():
        raise HTTPException(status_code=404, detail="User not found")
    return db.query(models.Post).filter(models.Post.user_id == user_id).all()


@app.get("/posts/{post_id}")
async def get_post(post_id: int, db: db_dep, _token: token_dep):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@app.post("/posts/", status_code=status.HTTP_201_CREATED)
async def create_post(post: PostCreate, db: db_dep, token: token_dep):
    user_id = int(token["sub"])
    if not db.query(models.User).filter(models.User.id == user_id).first():
        raise HTTPException(status_code=404, detail="User not found")
    db_post = models.Post(
        user_id=user_id,
        issue=post.issue,
        stat=post.stat,
        notes=post.notes,
        priority=post.priority,
    )
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post


@app.put("/posts/{post_id}")
async def update_post(post_id: int, post: PostUpdate, db: db_dep, token: token_dep):
    if token.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    db_post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not db_post:
        raise HTTPException(status_code=404, detail="Post not found")
    db_post.issue = post.issue
    db_post.stat = post.stat
    db_post.notes = post.notes
    db_post.priority = post.priority
    db.commit()
    db.refresh(db_post)
    return db_post


@app.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, db: db_dep, token: token_dep):
    if token.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    db_post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not db_post:
        raise HTTPException(status_code=404, detail="Post not found")
    db.delete(db_post)
    db.commit()
