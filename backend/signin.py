"""Signing in without a password: a one-time code sent by email, or a Google account.

Both find the account by its email address: a student's comes from the class
list (Import students, Add a student), the lecturer's from Settings. Nobody signs
up this way: an address that is on no account can't sign in, and the answer to
"send me a code" never says whether the address is on one.

  Email codes  need an outgoing mail server: SMTP_HOST, SMTP_PORT, SMTP_USER,
               SMTP_PASSWORD, SMTP_FROM (Gmail works, with an app password).
  Google       needs an OAuth client of type "Web application" from
               console.cloud.google.com: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
               with this server's callback address (callback_urls()) among its
               authorized redirect URIs.

SIGNIN_EMAIL=off or SIGNIN_GOOGLE=off turns one of them off and keeps its settings.

A sign-in ends where it started. The dashboard gets a one-time ticket in its
address and trades it for a token, so the token itself never shows in an
address. The student chat gets Chainlit's own sign-in cookie, the one its sign-in
page sets when a student types a password (student_app/app.py, auth_callback).
"""
import base64
import email.utils
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import smtplib
import socket
import ssl
import threading
import time
from collections import defaultdict
from email.message import EmailMessage
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from backend import db, names, tunnel

log = logging.getLogger("reins.signin")

CODE_MINUTES = 10
CODE_TRIES = 5          # wrong codes, after which every open code of the account stops working
RESEND_SECONDS = 30     # at most one new code per account in this time...
CODES_PER_HOUR = 6      # ...and this many an hour
_IP_WINDOW, _IP_MAX = 600, 120  # codes asked for from one address (a whole class may share one)

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
CALLBACK_PATH = "/api/login/google/callback"
STATE_COOKIE = "reins_google_state"
STATE_COOKIE_PATH = "/api/login/google"
FLOW_SECONDS = 600      # from leaving for Google to coming back
TICKET_SECONDS = 120    # from coming back to the dashboard trading its ticket

DESTINATIONS = ("dashboard", "chat")


# --- settings ------------------------------------------------------------------------


def switched_on(name: str) -> bool:
    """SIGNIN_EMAIL / SIGNIN_GOOGLE: on unless set to off."""
    return os.environ.get(name, "on").strip().lower() not in ("0", "off", "false", "no")


def smtp_config() -> dict[str, Any]:
    port_raw = os.environ.get("SMTP_PORT", "").strip()
    try:
        port = int(port_raw) if port_raw else 587
    except ValueError:
        port = 587
    user = os.environ.get("SMTP_USER", "").strip()
    security = os.environ.get("SMTP_SECURITY", "").strip().lower()
    if security not in ("ssl", "starttls", "none"):
        security = "ssl" if port == 465 else "starttls"
    return {
        "host": os.environ.get("SMTP_HOST", "").strip(),
        "port": port,
        "user": user,
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "sender": os.environ.get("SMTP_FROM", "").strip() or user,
        "security": security,
    }


def email_ready() -> bool:
    cfg = smtp_config()
    return bool(cfg["host"] and "@" in cfg["sender"])


def email_on() -> bool:
    return switched_on("SIGNIN_EMAIL") and email_ready()


def google_client() -> tuple[str, str]:
    return (os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
            os.environ.get("GOOGLE_CLIENT_SECRET", "").strip())


def google_ready() -> bool:
    return all(google_client())


def google_on() -> bool:
    return switched_on("SIGNIN_GOOGLE") and google_ready()


def chat_page() -> bool:
    """True when the student chat runs here with its own sign-in page, so a
    sign-in made here can hand it Chainlit's cookie."""
    if not tunnel.chat_path():
        return False
    try:
        from chainlit.config import config as cl_config
    except Exception:  # chainlit not installed: the chat runs elsewhere
        return False
    return cl_config.code.password_auth_callback is not None


def methods() -> dict[str, Any]:
    """What the sign-in pages offer, and the chat's language setting (auto, he
    or en) for the buttons the chat's sign-in page adds. Public: it says nothing
    about any account."""
    from backend import settings

    return {"password": True, "email": email_on(), "google": google_on(), "chat_page": chat_page(),
            "chat_language": settings.chat_language()}


def base_url(request) -> str:
    """This server's address as the browser sees it: Google sends the browser
    back here, and Google compares it with the client's registered addresses."""
    from backend import deps

    if not deps.is_local_request(request):
        fixed = (names.env("PUBLIC_URL") or "").strip().rstrip("/")
        if fixed:
            return fixed
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc)
    return f"{proto}://{host.split(',')[0].strip()}"


def callback_urls() -> list[str]:
    """The addresses to list as authorized redirect URIs in the Google client:
    this computer's, and the public one students use."""
    urls = [f"http://localhost:{tunnel.port()}{CALLBACK_PATH}"]
    public = []
    fixed = (names.env("PUBLIC_URL") or "").strip().rstrip("/")
    if fixed:
        public.append(fixed)
    if tunnel.ngrok_domain():
        public.append(f"https://{tunnel.ngrok_domain()}")
    student_url = os.environ.get("STUDENT_URL", "").strip()
    m = re.match(r"^(https://[^/]+)", student_url)
    if m:
        public.append(m.group(1))
    try:
        live = tunnel.status().get("public_url") or ""
    except Exception:
        live = ""
    m = re.match(r"^(https://[^/]+)", live)
    if m:
        public.append(m.group(1))
    for p in public:
        url = p + CALLBACK_PATH
        if url not in urls:
            urls.append(url)
    return urls


# --- accounts ------------------------------------------------------------------------

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_email(raw: Optional[str]) -> Optional[str]:
    e = (raw or "").strip().lower()
    return e if len(e) <= 200 and _EMAIL.match(e) else None


def account_for(email_addr: str, to: str):
    """(the account this address signs in to, "") or (None, why). The dashboard
    takes a lecturer's account; the chat a student's, or a lecturer's when the
    address is on no student account. why: "unknown", "student" (the dashboard,
    and the address is only a student's), "ambiguous" (more than one account)."""
    with db.conn() as c:
        rows = c.execute(
            "SELECT id, username, role, login_code FROM users WHERE lower(trim(email)) = ? ORDER BY id",
            (email_addr,),
        ).fetchall()
    if not rows:
        return None, "unknown"
    teachers = [r for r in rows if r["role"] == "teacher"]
    students = [r for r in rows if r["role"] != "teacher"]
    pick = teachers if to == "dashboard" else (students or teachers)
    if not pick:
        return None, "student"
    if len(pick) > 1:
        return None, "ambiguous"
    return pick[0], ""


def students_with_email() -> dict[str, int]:
    with db.conn() as c:
        row = c.execute(
            "SELECT COUNT(*) AS total, COUNT(NULLIF(trim(COALESCE(email, '')), '')) AS with_email "
            "FROM users WHERE role = 'student'"
        ).fetchone()
    return {"total": row["total"], "with_email": row["with_email"]}


# --- codes by email --------------------------------------------------------------------

_IP_ASKS: dict[str, list[float]] = defaultdict(list)


def _hash(code: str, salt: str) -> str:
    return salt + "$" + hashlib.sha256((salt + code).encode()).hexdigest()


def _matches(code: str, stored: str) -> bool:
    salt, _, _digest = stored.partition("$")
    return hmac.compare_digest(_hash(code, salt), stored)


def _dispatch(fn, *args) -> None:
    """Send in the background: the answer to "send me a code" shouldn't wait
    for the mail server, or take longer for an address that is an account's."""
    threading.Thread(target=fn, args=args, daemon=True).start()


def request_code(email_addr: str, to: str, lang: str, ip: str, allow_teacher: bool) -> str:
    """Email a sign-in code to this address when it is an account's. "sent" (also
    when it is no account's, or a code went out moments ago: the answer is the
    same), or "busy" when too many codes were asked for from this IP."""
    now = time.time()
    asks = [t for t in _IP_ASKS[ip] if now - t < _IP_WINDOW]
    if len(asks) >= _IP_MAX:
        _IP_ASKS[ip] = asks
        return "busy"
    asks.append(now)
    _IP_ASKS[ip] = asks
    row, _why = account_for(email_addr, to)
    if row is None or (row["role"] == "teacher" and not allow_teacher):
        return "sent"
    with db.conn() as c:
        recent = c.execute(
            "SELECT created_at FROM signin_codes WHERE user_id = ? AND created_at > ? ORDER BY created_at DESC",
            (row["id"], now - 3600),
        ).fetchall()
        if recent and (now - recent[0]["created_at"] < RESEND_SECONDS or len(recent) >= CODES_PER_HOUR):
            return "sent"
        code = f"{secrets.randbelow(10 ** 6):06d}"
        c.execute(
            "INSERT INTO signin_codes (user_id, code_hash, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (row["id"], _hash(code, secrets.token_hex(8)), now, now + CODE_MINUTES * 60),
        )
        c.execute("DELETE FROM signin_codes WHERE expires_at < ?", (now - 86400,))
    subject, text, html = code_message(code, lang)
    _dispatch(_send_quietly, email_addr, subject, text, html)
    return "sent"


def verify_code(email_addr: str, code: str, to: str, allow_teacher: bool):
    """(the account, "") when `code` is an open code sent to this address, or
    (None, why): "wrong" (wrong, used or expired), "blocked" (a lecturer's
    account, away from the lecturer's computer). A code works once; the first
    one that works closes every other code sent to the account."""
    row, _why = account_for(email_addr, to)
    code = re.sub(r"\s", "", code or "")
    if row is None or not re.fullmatch(r"\d{6}", code):
        return None, "wrong"
    now = time.time()
    with db.conn() as c:
        live = c.execute(
            "SELECT id, code_hash FROM signin_codes "
            "WHERE user_id = ? AND used = 0 AND expires_at > ? AND tries < ?",
            (row["id"], now, CODE_TRIES),
        ).fetchall()
        hit = next((r for r in live if _matches(code, r["code_hash"])), None)
        if hit is None:
            if live:
                marks = ",".join("?" * len(live))
                c.execute(f"UPDATE signin_codes SET tries = tries + 1 WHERE id IN ({marks})",
                          [r["id"] for r in live])
            return None, "wrong"
        if row["role"] == "teacher" and not allow_teacher:
            return None, "blocked"
        # Two requests with the same code at once: only one of them gets it.
        if c.execute("UPDATE signin_codes SET used = 1 WHERE id = ? AND used = 0", (hit["id"],)).rowcount != 1:
            return None, "wrong"
        c.execute("UPDATE signin_codes SET used = 1 WHERE user_id = ? AND used = 0", (row["id"],))
    return row, ""


_MAIL = {
    "he": {
        "subject": "קוד הכניסה ל־REINS Edu: {code}",
        "text": ("שלום,\n\n"
                 "קוד הכניסה שלך ל־REINS Edu הוא {code}\n"
                 "הקוד תקף ל־{minutes} דקות, ואפשר להשתמש בו פעם אחת.\n\n"
                 "לא ביקשת קוד? אפשר פשוט להתעלם מהמייל הזה.\n"),
        "lead": "קוד הכניסה שלך ל־REINS Edu:",
        "note": "הקוד תקף ל־{minutes} דקות, ואפשר להשתמש בו פעם אחת. לא ביקשת קוד? אפשר פשוט להתעלם מהמייל הזה.",
    },
    "en": {
        "subject": "Your REINS Edu sign-in code: {code}",
        "text": ("Hello,\n\n"
                 "Your REINS Edu sign-in code is {code}\n"
                 "It works once, for the next {minutes} minutes.\n\n"
                 "Didn't ask for a code? Just ignore this email.\n"),
        "lead": "Your REINS Edu sign-in code:",
        "note": "It works once, for the next {minutes} minutes. Didn't ask for a code? Just ignore this email.",
    },
}


def code_message(code: str, lang: str) -> tuple[str, str, str]:
    """(subject, plain text, HTML) of the email with a sign-in code."""
    m = _MAIL["he" if lang == "he" else "en"]
    dir_ = "rtl" if lang == "he" else "ltr"
    fill = {"code": code, "minutes": CODE_MINUTES}
    html = (f'<div dir="{dir_}" style="font-family:Arial,sans-serif;font-size:16px;color:#1f2328">'
            f'<p>{m["lead"]}</p>'
            f'<p dir="ltr" style="font-size:32px;font-weight:bold;letter-spacing:6px;margin:16px 0">{code}</p>'
            f'<p style="color:#59616a;font-size:14px">{m["note"].format(**fill)}</p></div>')
    return m["subject"].format(**fill), m["text"].format(**fill), html


def send_mail(to_addr: str, subject: str, text: str, html: Optional[str] = None) -> None:
    """Send one email through the SMTP server in the settings. Raises on failure."""
    cfg = smtp_config()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email.utils.formataddr(("REINS Edu", cfg["sender"]))
    msg["To"] = to_addr
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=cfg["sender"].rpartition("@")[2] or None)
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    context = ssl.create_default_context()
    if cfg["security"] == "ssl":
        server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20, context=context)
    else:
        server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=20)
    with server:
        if cfg["security"] == "starttls":
            server.starttls(context=context)
        if cfg["user"]:
            server.login(cfg["user"], cfg["password"])
        server.send_message(msg)


def _send_quietly(to_addr: str, subject: str, text: str, html: Optional[str]) -> None:
    try:
        send_mail(to_addr, subject, text, html)
    except Exception as e:  # the student sees no code arrive; the lecturer sees why in the log
        log.warning("couldn't send a sign-in code: %s", mail_error(e))


def mail_error(e: Exception) -> str:
    """What went wrong with the mail server, in words a lecturer can act on."""
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return ("The mail server refused the username or password. "
                "With Gmail, the password is an app password, not the account's own.")
    if isinstance(e, smtplib.SMTPSenderRefused):
        return "The mail server refused the sender's address. Use the address of the mail account."
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return "The mail server refused the recipient's address."
    if isinstance(e, ssl.SSLError):
        return "The secure connection failed: check the port (587 for STARTTLS, 465 for SSL)."
    if isinstance(e, (socket.gaierror, ConnectionRefusedError, socket.timeout, TimeoutError)):
        return "Couldn't reach the mail server. Check its address and port."
    if isinstance(e, smtplib.SMTPNotSupportedError):
        return "The mail server doesn't take this kind of connection: try the other port (587 or 465)."
    return f"The mail server answered: {e}"


# --- Google ----------------------------------------------------------------------------

_FLOWS: dict[str, dict[str, Any]] = {}       # state -> the sign-in on its way to Google and back
_TICKETS: dict[str, tuple[float, dict]] = {}  # ticket -> (made at, the dashboard's sign-in)


def _prune() -> None:
    now = time.time()
    for state in [s for s, f in _FLOWS.items() if now - f["at"] > FLOW_SECONDS]:
        _FLOWS.pop(state, None)
    for ticket in [t for t, (at, _) in _TICKETS.items() if now - at > TICKET_SECONDS]:
        _TICKETS.pop(ticket, None)


def google_start(to: str, redirect_uri: str) -> tuple[str, str]:
    """(Google's sign-in address to send the browser to, the state to keep in
    the browser's cookie). PKCE and a nonce as well as the state."""
    _prune()
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(16)
    _FLOWS[state] = {"to": to, "nonce": nonce, "verifier": verifier,
                     "redirect_uri": redirect_uri, "at": time.time()}
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    query = {
        "client_id": google_client()[0],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH}?{urlencode(query)}", state


def take_flow(state: str) -> Optional[dict[str, Any]]:
    """The sign-in this state belongs to (once), or None when it is unknown or too old."""
    flow = _FLOWS.pop(state, None) if state else None
    if flow is None or time.time() - flow["at"] > FLOW_SECONDS:
        return None
    return flow


async def google_email(flow: dict[str, Any], code: str) -> tuple[Optional[str], str]:
    """(the Google account's verified email, "") or (None, why): "google_error",
    "unverified"."""
    client_id, client_secret = google_client()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(GOOGLE_TOKEN, data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": flow["redirect_uri"],
                "grant_type": "authorization_code",
                "code_verifier": flow["verifier"],
            })
        if r.status_code != 200:
            log.warning("Google refused the sign-in code: %s %s", r.status_code, r.text[:300])
            return None, "google_error"
        claims = id_token_claims(r.json()["id_token"])
    except (httpx.HTTPError, KeyError, ValueError) as e:
        log.warning("Google sign-in failed: %s", e)
        return None, "google_error"
    return check_claims(claims, flow["nonce"], client_id)


def id_token_claims(token: str) -> dict[str, Any]:
    """The claims of an ID token. Its signature isn't checked: the token came
    straight from Google's token endpoint over HTTPS, in answer to this server's
    own client secret, which OpenID Connect Core (3.1.3.7) accepts in place of
    the signature. The claims are still checked (check_claims)."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def check_claims(claims: dict[str, Any], nonce: str, client_id: str) -> tuple[Optional[str], str]:
    if (claims.get("iss") not in _GOOGLE_ISSUERS or claims.get("aud") != client_id
            or float(claims.get("exp") or 0) < time.time()
            or not hmac.compare_digest(str(claims.get("nonce") or ""), nonce)):
        return None, "google_error"
    addr = clean_email(claims.get("email"))
    if not addr or claims.get("email_verified") not in (True, "true"):
        return None, "unverified"
    return addr, ""


def make_ticket(login: dict) -> str:
    _prune()
    ticket = secrets.token_urlsafe(24)
    _TICKETS[ticket] = (time.time(), login)
    return ticket


def use_ticket(ticket: str) -> Optional[dict]:
    at, login = _TICKETS.pop(ticket, (0.0, None)) if ticket else (0.0, None)
    return login if login is not None and time.time() - at <= TICKET_SECONDS else None


# --- the student chat ------------------------------------------------------------------


def chat_cookie(request, response, login: dict, login_code: str) -> None:
    """Sign this browser in to the student chat: Chainlit's own cookie, holding
    what its sign-in page would (student_app/app.py, auth_callback)."""
    from chainlit.auth import create_jwt, set_auth_cookie
    from chainlit.user import User

    user = User(identifier=login_code.strip().lower(), metadata={"login": login})
    set_auth_cookie(request, response, create_jwt(user))
