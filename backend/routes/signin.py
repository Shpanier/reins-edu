"""Signing in with an email code or a Google account (backend/signin.py), and
the lecturer's settings for both.

  GET  /api/login/methods          what the sign-in pages offer (public)
  POST /api/login/email            email me a sign-in code
  POST /api/login/email/verify     sign in with that code
  GET  /api/login/google           off to Google (?to=dashboard|chat)
  GET  /api/login/google/callback  back from Google
  POST /api/login/ticket           the dashboard trades the ticket it came back with

  GET  /api/settings/signin        the lecturer's settings page
  POST /api/settings/signin        save them (.env)
  POST /api/settings/signin/test   send a test email to the lecturer
  POST /api/settings/my-email      the lecturer's own address, to sign in with
"""
import asyncio
import os
import secrets
from typing import Literal, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from backend import auth, courses, db, deps, settings, signin, tunnel

router = APIRouter()

Destination = Literal["dashboard", "chat"]


def _lang(raw: Optional[str]) -> str:
    if raw in ("he", "en"):
        return raw
    forced = settings.chat_language()
    return forced if forced in ("he", "en") else "en"


def _allow_teacher(request: Request) -> bool:
    return not deps.teacher_blocked("teacher", request)


def _signed_in(row) -> dict:
    login = auth.issue_token(row)
    login["courses"] = courses.for_user(login["user_id"], login["role"])
    return login


@router.get("/login/methods")
def login_methods():
    return signin.methods()


# --- a code by email -------------------------------------------------------------------


class EmailRequest(BaseModel):
    email: str = Field(max_length=200)
    to: Destination = "chat"
    lang: Optional[str] = None


@router.post("/login/email")
def email_code(req: EmailRequest, request: Request):
    if not signin.email_on():
        raise HTTPException(404, "Signing in with an email code is off.")
    addr = signin.clean_email(req.email)
    if not addr:
        raise HTTPException(422, "That isn't an email address.")
    result = signin.request_code(addr, req.to, _lang(req.lang), deps.client_ip(request), _allow_teacher(request))
    if result == "busy":
        raise HTTPException(429, "Too many codes were asked for from here. Wait a few minutes and try again.")
    return {"sent": True, "minutes": signin.CODE_MINUTES}


class VerifyRequest(BaseModel):
    email: str = Field(max_length=200)
    code: str = Field(max_length=20)
    to: Destination = "chat"


@router.post("/login/email/verify")
def email_verify(req: VerifyRequest, request: Request):
    if not signin.email_on():
        raise HTTPException(404, "Signing in with an email code is off.")
    addr = signin.clean_email(req.email)
    row, why = signin.verify_code(addr, req.code, req.to, _allow_teacher(request)) if addr else (None, "wrong")
    if why == "blocked":
        raise HTTPException(403, "Instructor login is only allowed from the instructor's computer.")
    if row is None:
        raise HTTPException(401, "Wrong or expired code.")
    login = _signed_in(row)
    if req.to == "chat" and signin.chat_page():
        response = JSONResponse(login)
        signin.chat_cookie(request, response, login, row["login_code"])
        return response
    return login


# --- Google ----------------------------------------------------------------------------


def _back_with_error(to: str, why: str, addr: str = "") -> RedirectResponse:
    chat = tunnel.chat_path()
    if to == "chat" and chat:
        # The chat's sign-in page says why (public/reins-chat.js, in the student's language).
        url = f"{chat}/login?" + urlencode({"signin_error": why, **({"email": addr} if addr else {})})
    else:
        url = "/?" + urlencode({"signin_error": why})
    response = RedirectResponse(url, status_code=302)
    response.delete_cookie(signin.STATE_COOKIE, path=signin.STATE_COOKIE_PATH)
    return response


@router.get("/login/google")
def google_start(request: Request, to: str = "dashboard"):
    to = to if to in signin.DESTINATIONS else "dashboard"
    if not signin.google_on():
        return _back_with_error(to, "off")
    base = signin.base_url(request)
    # Google takes a plain http:// address only for localhost: a dashboard opened
    # at 127.0.0.1 continues there (the state cookie must come back to the same host).
    if base.startswith("http://127.0.0.1:") or base == "http://127.0.0.1":
        local = base.replace("http://127.0.0.1", "http://localhost", 1)
        return RedirectResponse(f"{local}/api/login/google?" + urlencode({"to": to}), 302)
    url, state = signin.google_start(to, base + signin.CALLBACK_PATH)
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(signin.STATE_COOKIE, state, max_age=signin.FLOW_SECONDS, httponly=True,
                        samesite="lax", secure=base.startswith("https://"), path=signin.STATE_COOKIE_PATH)
    return response


@router.get("/login/google/callback")
async def google_callback(request: Request, state: str = "", code: str = "", error: str = ""):
    flow = signin.take_flow(state)
    if flow is None:
        # Unknown or too old: back to where a student or the lecturer would be.
        to = "dashboard" if deps.is_local_request(request) else "chat"
        return _back_with_error(to, "expired")
    to = flow["to"]
    # The browser that came back must be the one that left: its cookie holds the state.
    if not secrets.compare_digest(request.cookies.get(signin.STATE_COOKIE, ""), state):
        return _back_with_error(to, "expired")
    if error or not code:
        return _back_with_error(to, "cancelled")
    addr, why = await signin.google_email(flow, code)
    if not addr:
        return _back_with_error(to, why)
    row, why = signin.account_for(addr, to)
    if row is None:
        return _back_with_error(to, why, addr)
    if deps.teacher_blocked(row["role"], request):
        return _back_with_error(to, "blocked")
    if to == "chat" and not signin.chat_page():
        return _back_with_error(to, "no_chat_page")
    login = _signed_in(row)
    if to == "chat":
        response = RedirectResponse(f"{tunnel.chat_path()}/", status_code=302)
        signin.chat_cookie(request, response, login, row["login_code"])
    else:
        response = RedirectResponse("/?" + urlencode({"signin": signin.make_ticket(login)}), status_code=302)
    response.delete_cookie(signin.STATE_COOKIE, path=signin.STATE_COOKIE_PATH)
    return response


class TicketRequest(BaseModel):
    ticket: str = Field(max_length=100)


@router.post("/login/ticket")
def use_ticket(req: TicketRequest, request: Request):
    login = signin.use_ticket(req.ticket)
    if login is None:
        raise HTTPException(401, "This sign-in has expired. Sign in again.")
    if deps.teacher_blocked(login.get("role", ""), request):
        raise HTTPException(403, "Instructor login is only allowed from the instructor's computer.")
    return login


# --- the lecturer's settings ---------------------------------------------------------------


def _my_email(teacher: dict) -> str:
    with db.conn() as c:
        row = c.execute("SELECT email FROM users WHERE id = ?", (teacher.get("id"),)).fetchone()
    return (row["email"] or "") if row else ""


def _restart_needed() -> bool:
    """A method is on, but the chat runs without its sign-in page: it gets one
    (and the Google and email buttons) when REINS Edu starts again."""
    return bool(tunnel.chat_path()) and (signin.email_on() or signin.google_on()) and not signin.chat_page()


def signin_status(teacher: dict) -> dict:
    cfg = signin.smtp_config()
    client_id, client_secret = signin.google_client()
    return {
        "email": {
            "on": signin.email_on(), "ready": signin.email_ready(), "switch": signin.switched_on("SIGNIN_EMAIL"),
            "host": cfg["host"], "port": cfg["port"], "user": cfg["user"], "sender": cfg["sender"],
            "security": cfg["security"], "password_set": bool(cfg["password"]),
        },
        "google": {
            "on": signin.google_on(), "ready": signin.google_ready(), "switch": signin.switched_on("SIGNIN_GOOGLE"),
            "client_id": client_id, "secret_set": bool(client_secret),
            "callback_urls": signin.callback_urls(),
        },
        "my_email": _my_email(teacher),
        "students": signin.students_with_email(),
        "chat_page": signin.chat_page(),
        "restart_needed": _restart_needed(),
    }


@router.get("/settings/signin")
def get_signin_settings(teacher: dict = Depends(deps.require_teacher)):
    return signin_status(teacher)


class SigninSettings(BaseModel):
    email_on: Optional[bool] = None
    smtp_host: Optional[str] = Field(default=None, max_length=200)
    smtp_port: Optional[int] = Field(default=None, ge=1, le=65535)
    smtp_user: Optional[str] = Field(default=None, max_length=200)
    # None or empty: keep the password already stored.
    smtp_password: Optional[str] = Field(default=None, max_length=500)
    smtp_from: Optional[str] = Field(default=None, max_length=200)
    smtp_security: Optional[Literal["starttls", "ssl", "none"]] = None
    google_on: Optional[bool] = None
    google_client_id: Optional[str] = Field(default=None, max_length=300)
    # None or empty: keep the secret already stored.
    google_client_secret: Optional[str] = Field(default=None, max_length=300)


@router.post("/settings/signin")
def save_signin_settings(req: SigninSettings, teacher: dict = Depends(deps.require_teacher)):
    updates: dict[str, str] = {}
    if req.email_on is not None:
        updates["SIGNIN_EMAIL"] = "on" if req.email_on else "off"
    if req.google_on is not None:
        updates["SIGNIN_GOOGLE"] = "on" if req.google_on else "off"
    for field, key in (("smtp_host", "SMTP_HOST"), ("smtp_user", "SMTP_USER"), ("smtp_from", "SMTP_FROM"),
                       ("smtp_security", "SMTP_SECURITY"), ("google_client_id", "GOOGLE_CLIENT_ID")):
        value = getattr(req, field)
        if value is not None:
            updates[key] = value.strip()
    if req.smtp_port is not None:
        updates["SMTP_PORT"] = str(req.smtp_port)
    if req.smtp_password:
        updates["SMTP_PASSWORD"] = req.smtp_password.strip()
    if req.google_client_secret:
        updates["GOOGLE_CLIENT_SECRET"] = req.google_client_secret.strip()
    if updates.get("SMTP_FROM") and "@" not in updates["SMTP_FROM"]:
        raise HTTPException(422, "The sender is an email address.")
    if updates:
        settings.save_env(updates)
    # The chat's sign-in page needs a secret to sign its sessions (installs from
    # before the start scripts made one have none).
    if (signin.email_on() or signin.google_on()) and not os.environ.get("CHAINLIT_AUTH_SECRET", "").strip():
        settings.save_env({"CHAINLIT_AUTH_SECRET": secrets.token_urlsafe(48)})
    return signin_status(teacher)


class TestEmail(BaseModel):
    to: Optional[str] = Field(default=None, max_length=200)
    lang: Optional[str] = None


@router.post("/settings/signin/test")
async def test_email(req: TestEmail, teacher: dict = Depends(deps.require_teacher)):
    if not signin.email_ready():
        return {"ok": False, "message": "Fill in the mail server and the sender first."}
    addr = signin.clean_email(req.to or _my_email(teacher))
    if not addr:
        return {"ok": False, "message": "Enter your own email address first."}
    lang = _lang(req.lang)
    subject, text, html = signin.code_message("123456", lang)
    subject = ("בדיקה: " if lang == "he" else "Test: ") + subject
    try:
        await asyncio.to_thread(signin.send_mail, addr, subject, text, html)
    except Exception as e:
        return {"ok": False, "message": signin.mail_error(e)}
    return {"ok": True, "message": f"Sent to {addr}.", "to": addr}


class MyEmail(BaseModel):
    email: str = Field(max_length=200)


@router.post("/settings/my-email")
def save_my_email(req: MyEmail, teacher: dict = Depends(deps.require_teacher)):
    raw = req.email.strip()
    addr = signin.clean_email(raw) if raw else ""
    if addr is None:
        raise HTTPException(422, "That isn't an email address.")
    if not teacher.get("id"):
        raise HTTPException(409, "Sign in with your lecturer account to set its address.")
    with db.conn() as c:
        if addr and c.execute("SELECT 1 FROM users WHERE role = 'teacher' AND id != ? AND lower(trim(email)) = ?",
                              (teacher["id"], addr)).fetchone():
            raise HTTPException(409, "Another lecturer account has this address.")
        c.execute("UPDATE users SET email = ? WHERE id = ?", (addr or None, teacher["id"]))
    return {"my_email": addr}
