from fastapi import FastAPI, HTTPException, Depends, status, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from typing import Annotated, Optional
from datetime import datetime
import models
from database import engine, SessionLocal
from sqlalchemy.orm import Session

app = FastAPI()
models.Base.metadata.create_all(bind=engine)

app.add_middleware(SessionMiddleware, secret_key="cisco-debug-secret-key")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class UserBase(BaseModel):
    id: int
    email: str
    pas_hash: str

class PostBase(BaseModel):
    id: int
    user_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    issue: str
    stat: str
    notes: Optional[str] = None
    priority: int

def getDB():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(getDB)]

def session_user(request: Request, db: Session):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(models.User).filter(models.User.id == user_id).first()


# --- JSON API routes ---

@app.post("/users/", status_code=status.HTTP_201_CREATED)
async def create_user(user: UserBase, db: db_dependency):
    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    db_user = models.User(email=user.email, pas_hash=user.pas_hash)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.get("/users/{user_id}")
async def get_user(user_id: int, db: db_dependency):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/posts/", status_code=status.HTTP_201_CREATED)
async def create_post(post: PostBase, db: db_dependency):
    user = db.query(models.User).filter(models.User.id == post.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="No user found with that user_id")
    db_post = models.Post(
        user_id=post.user_id,
        issue=post.issue,
        stat=post.stat,
        notes=post.notes,
        priority=post.priority
    )
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post

@app.get("/posts/")
async def get_posts(db: db_dependency):
    return db.query(models.Post).all()

@app.get("/users/{user_id}/posts")
async def get_posts_by_user(user_id: int, db: db_dependency):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return db.query(models.Post).filter(models.Post.user_id == user_id).all()

@app.get("/users/{user_id}/posts/{post_id}")
async def get_post_by_user(user_id: int, post_id: int, db: db_dependency):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    post = db.query(models.Post).filter(models.Post.id == post_id, models.Post.user_id == user_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found for this user")
    return post

@app.get("/posts/new", response_class=HTMLResponse)
async def new_post_form(request: Request, db: db_dependency):
    user = session_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    if user.role != "client":
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("post_form.html", {"request": request, "post": None, "user": user})

@app.get("/posts/{post_id}")
async def get_post(post_id: int, db: db_dependency):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post

@app.put("/posts/{post_id}")
async def update_post(post_id: int, post: PostBase, db: db_dependency):
    db_post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not db_post:
        raise HTTPException(status_code=404, detail="Post not found")
    db_post.user_id = post.user_id
    db_post.issue = post.issue
    db_post.stat = post.stat
    db_post.notes = post.notes
    db_post.priority = post.priority
    db.commit()
    db.refresh(db_post)
    return db_post

@app.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, db: db_dependency):
    db_post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not db_post:
        raise HTTPException(status_code=404, detail="Post not found")
    db.delete(db_post)
    db.commit()

@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: db_dependency):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    existing_posts = db.query(models.Post).filter(models.Post.user_id == user_id).first()
    if existing_posts:
        raise HTTPException(status_code=409, detail="Cannot delete user with existing posts. Delete their posts first.")
    db.delete(user)
    db.commit()


# --- Page routes ---

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, db: db_dependency, email: str = Form(...), password: str = Form(...)):
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or user.pas_hash != password:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid email or password"})
    request.session["user_id"] = user.id
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register(
    request: Request,
    db: db_dependency,
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
):
    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "An account with that email already exists.",
            "prefill_email": email,
        })
    if role not in ("client", "admin"):
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Invalid account type.",
            "prefill_email": email,
        })
    db_user = models.User(email=email, pas_hash=password, role=role)
    db.add(db_user)
    db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: db_dependency):
    user = session_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    if user.role == "client":
        posts = db.query(models.Post).filter(models.Post.user_id == user.id).all()
    else:
        posts = db.query(models.Post).all()
    users = {u.id: u.email for u in db.query(models.User).all()}
    return templates.TemplateResponse("dashboard.html", {"request": request, "posts": posts, "users": users, "user": user})

@app.post("/posts/create")
async def create_post_form(
    request: Request,
    db: db_dependency,
    issue: str = Form(...),
    stat: str = Form(...),
    notes: str = Form(None),
    priority: int = Form(0),
):
    user = session_user(request, db)
    if not user or user.role != "client":
        return RedirectResponse(url="/", status_code=303)
    db_post = models.Post(
        user_id=user.id,
        issue=issue,
        stat=stat,
        notes=notes or None,
        priority=priority,
    )
    db.add(db_post)
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/posts/{post_id}/edit", response_class=HTMLResponse)
async def edit_post_form(post_id: int, request: Request, db: db_dependency):
    user = session_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    if user.role != "admin":
        return RedirectResponse(url="/dashboard", status_code=303)
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return templates.TemplateResponse("post_form.html", {"request": request, "post": post, "user": user})

@app.post("/posts/{post_id}/update")
async def update_post_form(
    post_id: int,
    request: Request,
    db: db_dependency,
    issue: str = Form(...),
    stat: str = Form(...),
    notes: str = Form(None),
    priority: int = Form(0),
):
    user = session_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse(url="/", status_code=303)
    db_post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not db_post:
        raise HTTPException(status_code=404, detail="Post not found")
    db_post.issue = issue
    db_post.stat = stat
    db_post.notes = notes or None
    db_post.priority = priority
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/posts/{post_id}/delete")
async def delete_post_form(post_id: int, request: Request, db: db_dependency):
    user = session_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse(url="/", status_code=303)
    db_post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not db_post:
        raise HTTPException(status_code=404, detail="Post not found")
    db.delete(db_post)
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)
