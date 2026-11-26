"""Signing in with a code sent by email, or with a Google account (backend/signin.py).

No mail server and no Google: the mail is caught on its way out, and Google's
token endpoint is a fake that answers with an ID token made here.
"""
import base64
import json
import os
import smtplib
import tempfile
import time
from urllib.parse import parse_qs, urlparse

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.setdefault("GEMINI_API_KEY", "unused-in-signin-tests")

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import auth, db, signin
from backend.main import app

_ENV_KEYS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_SECURITY",
             "SIGNIN_EMAIL", "SIGNIN_GOOGLE", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
             "CHAINLIT_AUTH_SECRET", "REINS_PUBLIC_URL")
CLIENT_ID = "test-client.apps.googleusercontent.com"


@pytest.fixture(autouse=True)
def env():
    """Each test starts with no sign-in settings, and leaves none behind
    (the settings page writes straight into os.environ)."""
    before = {k: os.environ.get(k) for k in _ENV_KEYS}
    for k in _ENV_KEYS:
        os.environ.pop(k, None)
    signin._IP_ASKS.clear()
    yield
    for k, v in before.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _mail_on():
    os.environ.update(SMTP_HOST="smtp.example.org", SMTP_USER="sender@example.org", SMTP_PASSWORD="pw")


def _google_on():
    os.environ.update(GOOGLE_CLIENT_ID=CLIENT_ID, GOOGLE_CLIENT_SECRET="shh")


@pytest.fixture(scope="module")
def local():
    with TestClient(app, client=("127.0.0.1", 50001)) as tc:
        with db.conn() as c:
            for name, code, role, addr in (
                ("Signin Teacher", "SIGN-TEACH", "teacher", "lecturer@example.edu"),
                ("Signin Student", "SIGN-STU01", "student", "student1@example.edu"),
                ("Signin Twin A", "SIGN-TWINA", "student", "twins@example.edu"),
                ("Signin Twin B", "SIGN-TWINB", "student", "twins@example.edu"),
            ):
                c.execute("INSERT OR IGNORE INTO users (username, login_code, role, email) VALUES (?, ?, ?, ?)",
                          (name, code, role, addr))
        yield tc


@pytest.fixture(scope="module")
def remote(local):
    # A browser elsewhere (a student through the tunnel): not this computer.
    with TestClient(app, client=("203.0.113.7", 40000)) as tc:
        yield tc


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(signin, "_dispatch", lambda fn, *args: fn(*args))
    monkeypatch.setattr(signin, "send_mail", lambda to, subject, text, html=None: sent.append(
        {"to": to, "subject": subject, "text": text, "html": html}))
    return sent


def _code(mail):
    return mail["subject"].rsplit(" ", 1)[-1]


def _clear_codes(code):
    with db.conn() as c:
        c.execute("DELETE FROM signin_codes WHERE user_id = (SELECT id FROM users WHERE login_code = ?)", (code,))


def _teacher_token(tc):
    r = tc.post("/api/login", json={"code": "SIGN-TEACH", "password": "SIGN-TEACH"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# --- what is offered -------------------------------------------------------------------


def test_methods_follow_the_settings(local):
    m = local.get("/api/login/methods").json()
    assert (m["password"], m["email"], m["google"], m["chat_page"]) == (True, False, False, False)
    assert m["chat_language"] in ("auto", "he", "en")
    _mail_on()
    _google_on()
    m = local.get("/api/login/methods").json()
    assert m["email"] and m["google"]
    os.environ["SIGNIN_GOOGLE"] = "off"
    assert local.get("/api/login/methods").json()["google"] is False


def test_email_code_is_refused_while_off(remote):
    assert remote.post("/api/login/email", json={"email": "student1@example.edu"}).status_code == 404


# --- a code by email -------------------------------------------------------------------


def test_a_student_signs_in_with_a_code(remote, outbox):
    _mail_on()
    _clear_codes("SIGN-STU01")
    r = remote.post("/api/login/email", json={"email": " Student1@Example.edu ", "lang": "he"})
    assert r.status_code == 200 and r.json()["sent"]
    assert len(outbox) == 1 and outbox[0]["to"] == "student1@example.edu"
    code = _code(outbox[0])
    assert code.isdigit() and len(code) == 6 and code in outbox[0]["text"]
    assert "קוד הכניסה" in outbox[0]["subject"]

    wrong = f"{(int(code) + 1) % 10 ** 6:06d}"
    assert remote.post("/api/login/email/verify",
                       json={"email": "student1@example.edu", "code": wrong}).status_code == 401
    r = remote.post("/api/login/email/verify", json={"email": "student1@example.edu", "code": code})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "student" and "courses" in body
    assert auth.user_for_token(body["token"])["username"] == "Signin Student"
    # Once only.
    assert remote.post("/api/login/email/verify",
                       json={"email": "student1@example.edu", "code": code}).status_code == 401


def test_an_unknown_address_gets_the_same_answer_and_no_mail(remote, outbox):
    _mail_on()
    r = remote.post("/api/login/email", json={"email": "nobody@example.edu"})
    assert r.status_code == 200 and r.json()["sent"]
    assert outbox == []
    assert remote.post("/api/login/email", json={"email": "not an address"}).status_code == 422


def test_an_address_on_two_accounts_signs_in_to_neither(remote, outbox):
    _mail_on()
    assert remote.post("/api/login/email", json={"email": "twins@example.edu"}).status_code == 200
    assert outbox == []


def test_asking_again_at_once_sends_no_second_code(remote, outbox):
    _mail_on()
    _clear_codes("SIGN-STU01")
    remote.post("/api/login/email", json={"email": "student1@example.edu"})
    remote.post("/api/login/email", json={"email": "student1@example.edu"})
    assert len(outbox) == 1


def test_five_wrong_codes_close_the_code(remote, outbox):
    _mail_on()
    _clear_codes("SIGN-STU01")
    remote.post("/api/login/email", json={"email": "student1@example.edu"})
    code = _code(outbox[0])
    wrong = f"{(int(code) + 1) % 10 ** 6:06d}"
    for _ in range(signin.CODE_TRIES):
        remote.post("/api/login/email/verify", json={"email": "student1@example.edu", "code": wrong})
    assert remote.post("/api/login/email/verify",
                       json={"email": "student1@example.edu", "code": code}).status_code == 401


def test_an_expired_code_fails(remote, outbox):
    _mail_on()
    _clear_codes("SIGN-STU01")
    remote.post("/api/login/email", json={"email": "student1@example.edu"})
    with db.conn() as c:
        c.execute("UPDATE signin_codes SET expires_at = ?", (time.time() - 1,))
    assert remote.post("/api/login/email/verify",
                       json={"email": "student1@example.edu", "code": _code(outbox[0])}).status_code == 401


def test_the_lecturer_signs_in_with_a_code_only_on_their_computer(local, remote, outbox):
    _mail_on()
    _clear_codes("SIGN-TEACH")
    remote.post("/api/login/email", json={"email": "lecturer@example.edu", "to": "dashboard"})
    assert outbox == []
    local.post("/api/login/email", json={"email": "lecturer@example.edu", "to": "dashboard"})
    assert len(outbox) == 1
    r = local.post("/api/login/email/verify",
                   json={"email": "lecturer@example.edu", "code": _code(outbox[0]), "to": "dashboard"})
    assert r.status_code == 200 and r.json()["role"] == "teacher"


def test_a_students_address_opens_no_dashboard(local, outbox):
    _mail_on()
    local.post("/api/login/email", json={"email": "student1@example.edu", "to": "dashboard"})
    assert outbox == []


# --- Google ----------------------------------------------------------------------------


def _id_token(**claims):
    def part(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{part({'alg': 'RS256'})}.{part(claims)}.signature"


@pytest.fixture
def google(monkeypatch):
    """Google's token endpoint, answering with an ID token for `who["email"]`."""
    who = {"email": "lecturer@example.edu", "email_verified": True}
    seen = {}
    real = httpx.AsyncClient

    def handler(request):
        form = parse_qs(request.content.decode())
        seen.update({k: v[0] for k, v in form.items()})
        flow_nonce = who.get("nonce") or seen_nonce["value"]
        return httpx.Response(200, json={"id_token": _id_token(
            iss="https://accounts.google.com", aud=CLIENT_ID, exp=time.time() + 300,
            nonce=flow_nonce, email=who["email"], email_verified=who["email_verified"])})

    seen_nonce = {"value": ""}
    monkeypatch.setattr(signin.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return {"who": who, "seen": seen, "nonce": seen_nonce}


def _go_to_google(tc, google, to="dashboard"):
    r = tc.get(f"/api/login/google?to={to}", follow_redirects=False)
    assert r.status_code == 302, r.text
    url = urlparse(r.headers["location"])
    assert url.netloc == "accounts.google.com"
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert q["client_id"] == CLIENT_ID and q["code_challenge_method"] == "S256"
    assert q["redirect_uri"].endswith("/api/login/google/callback")
    google["nonce"]["value"] = q["nonce"]
    return q


def test_the_lecturer_signs_in_with_google(local, google):
    _google_on()
    q = _go_to_google(local, google)
    r = local.get(f"/api/login/google/callback?state={q['state']}&code=abc", follow_redirects=False)
    assert r.status_code == 302, r.text
    where = urlparse(r.headers["location"])
    assert where.path == "/" and "signin" in parse_qs(where.query)
    assert google["seen"]["code"] == "abc" and google["seen"]["code_verifier"]
    ticket = parse_qs(where.query)["signin"][0]
    body = local.post("/api/login/ticket", json={"ticket": ticket}).json()
    assert body["role"] == "teacher" and auth.user_for_token(body["token"])["username"] == "Signin Teacher"
    # A ticket works once.
    assert local.post("/api/login/ticket", json={"ticket": ticket}).status_code == 401


def test_google_back_in_another_browser_fails(local, google):
    _google_on()
    q = _go_to_google(local, google)
    local.cookies.clear()
    r = local.get(f"/api/login/google/callback?state={q['state']}&code=abc", follow_redirects=False)
    assert "signin_error=expired" in r.headers["location"]


def test_google_with_an_address_on_no_account(local, google):
    _google_on()
    google["who"]["email"] = "stranger@gmail.com"
    q = _go_to_google(local, google)
    r = local.get(f"/api/login/google/callback?state={q['state']}&code=abc", follow_redirects=False)
    assert "signin_error=unknown" in r.headers["location"]


def test_google_with_an_unverified_address(local, google):
    _google_on()
    google["who"]["email_verified"] = False
    q = _go_to_google(local, google)
    r = local.get(f"/api/login/google/callback?state={q['state']}&code=abc", follow_redirects=False)
    assert "signin_error=unverified" in r.headers["location"]


def test_google_cancelled(local, google):
    _google_on()
    q = _go_to_google(local, google)
    r = local.get(f"/api/login/google/callback?state={q['state']}&error=access_denied", follow_redirects=False)
    assert "signin_error=cancelled" in r.headers["location"]


def test_google_off_sends_back_with_a_reason(local):
    r = local.get("/api/login/google?to=dashboard", follow_redirects=False)
    assert "signin_error=off" in r.headers["location"]


def test_google_claims_are_checked():
    good = {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "exp": time.time() + 60,
            "nonce": "n1", "email": "A@B.org", "email_verified": True}
    assert signin.check_claims(good, "n1", CLIENT_ID) == ("a@b.org", "")
    for bad in ({"aud": "someone-else"}, {"iss": "https://evil.example"}, {"exp": time.time() - 1},
                {"nonce": "other"}):
        assert signin.check_claims({**good, **bad}, "n1", CLIENT_ID) == (None, "google_error")
    assert signin.check_claims({**good, "email_verified": False}, "n1", CLIENT_ID) == (None, "unverified")


def test_127_0_0_1_continues_at_localhost(local):
    _google_on()
    r = local.get("/api/login/google?to=dashboard", headers={"host": "127.0.0.1:8010"}, follow_redirects=False)
    assert r.headers["location"].startswith("http://localhost:8010/api/login/google?")


# --- the student chat ----------------------------------------------------------------------


def test_the_chat_cookie_is_one_chainlit_accepts():
    from chainlit.auth import decode_jwt, get_token_from_cookies
    from starlette.requests import Request
    from starlette.responses import Response

    os.environ["CHAINLIT_AUTH_SECRET"] = "a-test-secret-that-is-long-enough-for-hs256"
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""})
    response = Response()
    login = {"token": "t0k", "user_id": 7, "username": "Signin Student", "role": "student", "courses": []}
    signin.chat_cookie(request, response, login, "SIGN-STU01")
    cookies = {}
    for header in response.headers.getlist("set-cookie"):
        name, _, rest = header.partition("=")
        cookies[name] = rest.split(";", 1)[0]
    user = decode_jwt(get_token_from_cookies(cookies))
    assert user.identifier == "sign-stu01" and user.metadata["login"]["token"] == "t0k"


# --- the lecturer's settings -----------------------------------------------------------------


def test_settings_never_return_the_secrets(local):
    hdr = _teacher_token(local)
    r = local.post("/api/settings/signin", headers=hdr, json={
        "smtp_host": "smtp.gmail.com", "smtp_port": 587, "smtp_user": "me@gmail.com",
        "smtp_password": "app-password", "google_client_id": CLIENT_ID, "google_client_secret": "shh"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"]["on"] and body["google"]["on"]
    assert body["email"]["password_set"] and body["google"]["secret_set"]
    assert "app-password" not in r.text and "shh" not in r.text
    assert any(u.startswith("http://localhost:") for u in body["google"]["callback_urls"])
    # The chat's sign-in page needs a secret: made when a method is turned on.
    assert os.environ.get("CHAINLIT_AUTH_SECRET")
    # An empty password keeps the stored one.
    local.post("/api/settings/signin", headers=hdr, json={"smtp_password": "", "email_on": False})
    assert os.environ["SMTP_PASSWORD"] == "app-password" and os.environ["SIGNIN_EMAIL"] == "off"


def test_students_cant_read_the_settings(remote, outbox):
    _mail_on()
    _clear_codes("SIGN-STU01")
    remote.post("/api/login/email", json={"email": "student1@example.edu"})
    token = remote.post("/api/login/email/verify",
                        json={"email": "student1@example.edu", "code": _code(outbox[0])}).json()["token"]
    assert remote.get("/api/settings/signin", headers={"Authorization": f"Bearer {token}"}).status_code == 403


def test_the_lecturer_sets_their_own_address(local):
    hdr = _teacher_token(local)
    assert local.post("/api/settings/my-email", headers=hdr, json={"email": "nope"}).status_code == 422
    r = local.post("/api/settings/my-email", headers=hdr, json={"email": " Lecturer@Example.edu "})
    assert r.json() == {"my_email": "lecturer@example.edu"}
    assert local.get("/api/settings/signin", headers=hdr).json()["my_email"] == "lecturer@example.edu"


def test_a_test_email_says_what_went_wrong(local, monkeypatch):
    hdr = _teacher_token(local)
    _mail_on()

    def refuse(*a, **k):
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr(signin, "send_mail", refuse)
    r = local.post("/api/settings/signin/test", headers=hdr, json={"to": "lecturer@example.edu"}).json()
    assert r["ok"] is False and "app password" in r["message"]
    monkeypatch.setattr(signin, "send_mail", lambda *a, **k: None)
    assert local.post("/api/settings/signin/test", headers=hdr, json={}).json()["ok"] is True


def test_the_chat_hears_why_google_failed(local, monkeypatch):
    # The chat's sign-in page (public/reins-chat.js) says it in the student's language.
    monkeypatch.setattr(signin.tunnel, "chat_path", lambda: "/chat")
    r = local.get("/api/login/google?to=chat", follow_redirects=False)
    assert r.headers["location"] == "/chat/login?signin_error=off"
