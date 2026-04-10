# Cisco Debug Database

A web application for tracking and managing Cisco network debug issues. Clients submit issues they are experiencing, and admins review and update them.

---

## What It Does

- **Clients** can create an account, log in, submit issues, and view the status of their own tickets
- **Admins** can view all submitted issues across all users, edit ticket details and status, and delete tickets

---

## Architecture

The application is split into two separate processes that communicate over HTTPS:

```
Browser
  │  HTTPS (port 8000)
  ▼
Client  (client/main.py)
  │  HTTPS + JWT Bearer (port 8443)
  ▼
API Server  (main.py)
  │  SQLAlchemy
  ▼
MySQL  (cisco database)
```

### API Server (`main.py`)
The backend. The only process that touches the database. Exposes a REST API and enforces authentication and authorization on every route. Runs on port `8443`.

### Web Client (`client/main.py`)
The frontend. Serves the HTML pages and handles form submissions. Has no direct database connection — it sends requests to the API server on behalf of the user. Runs on port `8000`.

---

## Authentication

The app uses a **JWT access + refresh token** flow.

1. The user logs in via the web client
2. The client forwards the credentials to the API server
3. The server validates them and returns a short-lived **access token** (15 minutes) and a long-lived **refresh token** (7 days)
4. The client stores both tokens in an encrypted session cookie
5. Every API call from the client includes the access token as a `Bearer` header
6. If the server rejects a request with `401` (expired access token), the client automatically exchanges the refresh token for a new pair of tokens and retries the request — the user never sees an interruption
7. If the refresh token is also expired or invalid, the session is cleared and the user is redirected to the login page

---

## Project Structure

```
main.py          — API server (routes, DB access, JWT enforcement)
auth.py          — JWT token creation and verification
database.py      — SQLAlchemy engine and session setup
models.py        — User and Post database models
client/
    main.py      — Web client (HTML routes, form handling, API calls)
    templates/   — Jinja2 HTML templates
    static/      — CSS stylesheet
certs/
    gen_certs.py — Script to generate self-signed TLS certificates
    server.key   — TLS private key
    server.crt   — TLS certificate
requirements.txt
```

---

## Database Models

**User**
| Column | Type | Notes |
|---|---|---|
| id | int | Primary key |
| email | varchar | Unique |
| pas_hash | varchar | Password |
| role | enum | `client` or `admin` |

**Post** (an issue ticket)
| Column | Type | Notes |
|---|---|---|
| id | int | Primary key |
| user_id | int | Foreign key → users |
| issue | varchar | Description of the issue |
| stat | enum | `Issue submitted`, `In review`, `Issue resolved` |
| priority | int | 0 = low, 1 = medium, 2+ = high |
| notes | text | Optional admin notes |
| created_at | timestamp | Set on insert |
| updated_at | timestamp | Updated on edit |

---

## Setup

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Create the MySQL database**
```sql
CREATE DATABASE cisco;
```

**3. Configure the database connection**

Edit `database.py` and set the correct credentials:
```python
URL_DATABASE = 'mysql+pymysql://user:password@localhost/cisco'
```

**4. Generate TLS certificates**
```bash
python certs/gen_certs.py
```

**5. Start the API server**
```bash
uvicorn main:app --ssl-keyfile certs/server.key --ssl-certfile certs/server.crt --port 8443
```

**6. Start the web client** (separate terminal)
```bash
uvicorn client.main:app --ssl-keyfile certs/server.key --ssl-certfile certs/server.crt --port 8000
```

**7. Open the app**

Navigate to `https://localhost:8000` in your browser. Expect a self-signed certificate warning in development — click through it.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET_KEY` | *(insecure default)* | Secret used to sign JWTs — **change in production** |
| `SESSION_SECRET` | *(insecure default)* | Secret used to sign the client session cookie — **change in production** |
| `API_SERVER_URL` | `https://localhost:8443` | URL the client uses to reach the API server |
| `SSL_CERT_PATH` | `false` | Path to the server CA cert for client verification, or `false` to skip (dev only) |
