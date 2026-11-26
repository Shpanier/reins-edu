"""The student's own copy of a lab (backend/my_work.py, GET /api/my-work/{id}):
one HTML page with how far they got and the whole conversation, only for the
session's own student (and teachers), with whatever anyone wrote shown and
never run."""
import copy
import os
import re
import tempfile

os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))
os.environ.setdefault("GEMINI_API_KEY", "unused-in-my-work-tests")

import pytest
from fastapi.testclient import TestClient

from backend import db, exercises
from backend.main import app

LAB = "my-work-lab-test"
QUIET = "my-work-quiet-test"  # keeps no transcript
STEPS = [
    {"label": "A1", "title": "Pull", "text": "Run `docker pull alpine`.",
     "expect_output": [r"alpine:3\.20"]},
    {"label": "A2", "title": "Read", "text": "Read this."},
    {"label": "B1", "title": "Last", "text": "The end."},
]


@pytest.fixture(scope="module")
def client():
    with TestClient(app, client=("127.0.0.1", 50000)) as tc:
        for ex_id, extra in ((LAB, {}), (QUIET, {"chat_history": False})):
            lab = copy.deepcopy(exercises.get("ex3-mcalc"))
            lab.update({"exercise_id": ex_id, "steps": copy.deepcopy(STEPS), "pacing": "class",
                        "open_steps": 3, "title_en": f"Lab {ex_id}", **extra})
            exercises._LOADED[ex_id] = lab
        with db.conn() as c:
            c.execute("INSERT OR IGNORE INTO users (username, login_code, role) "
                      "VALUES ('Work Teacher', 'MW-T', 'teacher')")
        yield tc
        for ex_id in (LAB, QUIET):
            exercises._LOADED.pop(ex_id, None)


def _login(tc, code, role="student"):
    with db.conn() as c:
        c.execute("INSERT OR IGNORE INTO users (username, login_code, role) VALUES (?, ?, ?)", (code, code, role))
    tok = tc.post("/api/login", json={"code": code, "password": code}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _session(tc, h, exercise_id):
    exercises.set_active(exercise_id)  # students outside every course open the active exercise
    try:
        r = tc.post("/api/sessions", json={"exercise_id": exercise_id}, headers=h)
    finally:
        exercises.set_active("ex3-mcalc")
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


def _write(tc, h, sid, *entries):
    r = tc.post(f"/api/transcript/{sid}", headers=h, json={"entries": list(entries), "client": "test"})
    assert r.status_code == 200, r.text


def test_the_page_holds_the_steps_the_outputs_and_the_conversation(client):
    h = _login(client, "MW-1")
    sid = _session(client, h, LAB)
    _write(client, h, sid,
           {"author": "tutor", "kind": "step", "step": 1, "content": "### Step A1 · Pull\n\nRun `docker pull alpine`."},
           {"author": "student", "kind": "output", "step": 1, "content": "docker.io/library/alpine:3.20\n<done>"},
           {"author": "tutor", "kind": "result", "step": 1, "content": "✅ Step A1 is done."},
           {"author": "student", "kind": "text", "content": "Why <script>alert(1)</script> here?\nsecond line"},
           {"author": "tutor", "kind": "text", "content": "Because **containers** share the kernel."})
    r = client.post("/api/steps/finish", headers=h,
                    json={"session_id": sid, "step": 1, "output": "docker.io/library/alpine:3.20"})
    assert r.json()["status"] == "done", r.text

    r = client.get(f"/api/my-work/{sid}", headers=h, params={"lang": "en"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    assert re.fullmatch(rf'attachment; filename="my-work-{LAB}-\d{{4}}-\d{{2}}-\d{{2}}\.html"',
                        r.headers["content-disposition"])
    page = r.text
    assert page.startswith("<!doctype html>") and '<html lang="en" dir="ltr">' in page
    assert f"My work: Lab {LAB}" in page and "MW-1" in page
    # How far they got: A1 done, A2 next, B1 later.
    assert "You finished 1 of 3 steps." in page
    assert "✅ Step A1 · Pull" in page and "▶️ Step A2 · Read" in page and "⬜ Step B1 · Last" in page
    # The conversation, in order, as Markdown made into HTML.
    assert page.index("Step A1 · Pull</h3>") < page.index("My output · step A1") < page.index("Because")
    assert '<pre class="output">docker.io/library/alpine:3.20\n&lt;done&gt;</pre>' in page
    assert "<strong>containers</strong>" in page and "<code>docker pull alpine</code>" in page
    # What the student wrote is shown, never run; their new line stays a new line.
    assert "<script>" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "here?<br />" in page
    # Each paragraph takes its direction from its own text (Hebrew right to left).
    assert '<p dir="auto">' in page


def test_the_page_speaks_the_language_asked_for(client):
    h = _login(client, "MW-2")
    sid = _session(client, h, LAB)
    page = client.get(f"/api/my-work/{sid}", headers=h, params={"lang": "he"}).text
    assert '<html lang="he" dir="rtl">' in page and "העבודה שלי" in page
    assert "סיימתם 0 מתוך 3 שלבים." in page
    assert "עוד אין כאן כלום" in page  # nothing written yet
    assert client.get(f"/api/my-work/{sid}", headers=h, params={"lang": "fr"}).status_code == 422


def test_only_the_student_and_teachers_get_it(client):
    owner = _login(client, "MW-3")
    sid = _session(client, owner, LAB)
    other = _login(client, "MW-4")
    teacher = _login(client, "MW-T", role="teacher")
    assert client.get(f"/api/my-work/{sid}").status_code == 401
    assert client.get(f"/api/my-work/{sid}", headers=other).status_code == 403
    assert client.get(f"/api/my-work/{sid}", headers=teacher).status_code == 200
    assert client.get("/api/my-work/no-such-session", headers=owner).status_code == 404


def test_without_a_transcript_the_page_has_what_the_server_kept(client):
    h = _login(client, "MW-5")
    sid = _session(client, h, QUIET)
    r = client.post("/api/steps/finish", headers=h,
                    json={"session_id": sid, "step": 1, "output": "pulled alpine:3.20 <ok>"})
    assert r.json()["status"] == "done", r.text
    page = client.get(f"/api/my-work/{sid}", headers=h, params={"lang": "en"}).text
    assert "What you sent, in order" in page
    assert "My output · step A1" in page and '<pre class="output">pulled alpine:3.20 &lt;ok&gt;</pre>' in page
    assert "You finished 1 of 3 steps." in page
