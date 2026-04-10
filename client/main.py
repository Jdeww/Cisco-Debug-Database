import os
from datetime import datetime
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
import httpx

app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "cisco-client-session-secret"),
)

_CLIENT_DIR = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(_CLIENT_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_CLIENT_DIR, "templates"))

# URL of the API server
SERVER_URL = os.getenv("API_SERVER_URL", "https://localhost:8443")

# For development with self-signed certs use False.
# In production set to the path of the server's CA cert, e.g. "certs/server.crt"
SSL_VERIFY: bool | str = os.getenv("SSL_CERT_PATH", "false")
if isinstance(SSL_VERIFY, str) and SSL_VERIFY.lower() == "false":
    SSL_VERIFY = False


def _auth_headers(request: Request) -> dict:
    token = request.session.get("access_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _session_user(request: Request) -> dict | None:
    if not request.session.get("access_token"):
        return None
    return {
        "id": request.session["user_id"],
        "email": request.session["email"],
        "role": request.session["role"],
    }


async def _api_request(request: Request, method: str, url: str, **kwargs) -> httpx.Response | None:
    """
    Makes an authenticated request to the API server.

    If the server returns 401 (expired access token), automatically calls
    /auth/refresh with the stored refresh token and retries once.
    Both tokens are rotated in the session on a successful refresh.

    Returns None if authentication cannot be recovered — the caller should
    redirect the user to the login page.
    """
    async with httpx.AsyncClient(verify=SSL_VERIFY) as client:
        resp = await getattr(client, method)(url, headers=_auth_headers(request), **kwargs)
        if resp.status_code != 401:
            return resp

        # Access token rejected — attempt a refresh
        refresh_token = request.session.get("refresh_token")
        if not refresh_token:
            request.session.clear()
            return None

        refresh_resp = await client.post(
            f"{SERVER_URL}/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        if refresh_resp.status_code != 200:
            request.session.clear()
            return None

        # Store the rotated tokens and retry the original request
        tokens = refresh_resp.json()
        request.session["access_token"] = tokens["access_token"]
        request.session["refresh_token"] = tokens["refresh_token"]
        return await getattr(client, method)(url, headers=_auth_headers(request), **kwargs)


def _parse_post_dates(posts: list) -> list:
    """Convert ISO datetime strings from the API into datetime objects for templates."""
    for post in posts:
        raw = post.get("created_at")
        if raw:
            try:
                post["created_at"] = datetime.fromisoformat(raw)
            except (ValueError, TypeError):
                post["created_at"] = None
    return posts


# --- Auth pages ---

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    async with httpx.AsyncClient(verify=SSL_VERIFY) as client:
        resp = await client.post(
            f"{SERVER_URL}/auth/login",
            json={"email": email, "password": password},
        )
    if resp.status_code != 200:
        error = resp.json().get("detail", "Login failed")
        return templates.TemplateResponse("login.html", {"request": request, "error": error})
    data = resp.json()
    request.session["access_token"] = data["access_token"]
    request.session["refresh_token"] = data["refresh_token"]
    request.session["user_id"] = data["user_id"]
    request.session["role"] = data["role"]
    request.session["email"] = data["email"]
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
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
):
    async with httpx.AsyncClient(verify=SSL_VERIFY) as client:
        resp = await client.post(
            f"{SERVER_URL}/auth/register",
            json={"email": email, "password": password, "role": role},
        )
    if resp.status_code != 201:
        error = resp.json().get("detail", "Registration failed")
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": error, "prefill_email": email},
        )
    return RedirectResponse(url="/", status_code=303)


# --- Dashboard ---

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = _session_user(request)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    if user["role"] == "client":
        posts_resp = await _api_request(request, "get", f"{SERVER_URL}/users/{user['id']}/posts")
        if posts_resp is None:
            return RedirectResponse(url="/", status_code=303)
        users: dict = {}
    else:
        posts_resp = await _api_request(request, "get", f"{SERVER_URL}/posts/")
        if posts_resp is None:
            return RedirectResponse(url="/", status_code=303)
        users_resp = await _api_request(request, "get", f"{SERVER_URL}/users/")
        if users_resp is None:
            return RedirectResponse(url="/", status_code=303)
        users = {u["id"]: u["email"] for u in users_resp.json()}
    posts = _parse_post_dates(posts_resp.json())
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "posts": posts, "users": users, "user": user},
    )


# --- Post forms ---

@app.get("/posts/new", response_class=HTMLResponse)
async def new_post_form(request: Request):
    user = _session_user(request)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    if user["role"] != "client":
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(
        "post_form.html", {"request": request, "post": None, "user": user}
    )


@app.post("/posts/create")
async def create_post(
    request: Request,
    issue: str = Form(...),
    stat: str = Form(...),
    notes: str = Form(None),
    priority: int = Form(0),
):
    user = _session_user(request)
    if not user or user["role"] != "client":
        return RedirectResponse(url="/", status_code=303)
    resp = await _api_request(
        request, "post", f"{SERVER_URL}/posts/",
        json={"issue": issue, "stat": stat, "notes": notes or None, "priority": priority},
    )
    if resp is None:
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/posts/{post_id}/edit", response_class=HTMLResponse)
async def edit_post_form(post_id: int, request: Request):
    user = _session_user(request)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    if user["role"] != "admin":
        return RedirectResponse(url="/dashboard", status_code=303)
    resp = await _api_request(request, "get", f"{SERVER_URL}/posts/{post_id}")
    if resp is None:
        return RedirectResponse(url="/", status_code=303)
    if resp.status_code == 404:
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(
        "post_form.html",
        {"request": request, "post": resp.json(), "user": user},
    )


@app.post("/posts/{post_id}/update")
async def update_post(
    post_id: int,
    request: Request,
    issue: str = Form(...),
    stat: str = Form(...),
    notes: str = Form(None),
    priority: int = Form(0),
):
    user = _session_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse(url="/", status_code=303)
    resp = await _api_request(
        request, "put", f"{SERVER_URL}/posts/{post_id}",
        json={"issue": issue, "stat": stat, "notes": notes or None, "priority": priority},
    )
    if resp is None:
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url="/dashboard", status_code=303)


@app.post("/posts/{post_id}/delete")
async def delete_post(post_id: int, request: Request):
    user = _session_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse(url="/", status_code=303)
    resp = await _api_request(request, "delete", f"{SERVER_URL}/posts/{post_id}")
    if resp is None:
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url="/dashboard", status_code=303)
