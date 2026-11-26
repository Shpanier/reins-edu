"""The student chat's own lines (student_app/chat_texts.py): every line exists
in Hebrew and in English, with the same placeholders, and every line the chat
asks for exists."""
import ast
import re
import string
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "student_app"))

import chat_texts  # noqa: E402

_HEBREW = re.compile(r"[֐-׿]")


def _fields(s: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(s) if name}


def test_every_line_has_both_languages_with_the_same_placeholders():
    for key, (he, en) in chat_texts.TEXTS.items():
        assert he.strip() and en.strip(), key
        assert _HEBREW.search(he), f"{key}: the Hebrew half has no Hebrew"
        assert not _HEBREW.search(en), f"{key}: the English half has Hebrew in it"
        assert _fields(he) == _fields(en), f"{key}: placeholders differ"


def test_text_fills_placeholders_in_the_chosen_language():
    assert chat_texts.text("btn_done", "en", label="A2") == "✅ Done with step A2"
    assert "A2" in chat_texts.text("btn_done", "he", label="A2")
    assert chat_texts.text("lab_done", "fr") == chat_texts.TEXTS["lab_done"][1]  # anything else: English


def test_the_chat_only_asks_for_lines_that_exist_and_has_no_hebrew_of_its_own():
    source = (ROOT / "student_app" / "app.py").read_text(encoding="utf-8")
    def names(arg):
        """The line names in _t(...)'s first argument: a string, or `"a" if x else "b"`."""
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            yield arg.value
        elif isinstance(arg, ast.IfExp):
            yield from names(arg.body)
            yield from names(arg.orelse)

    asked = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_t" and node.args:
            asked.update(names(node.args[0]))  # f"mode_{mode}" is checked below
    assert len(asked) > 50
    missing = {k for k in asked if k not in chat_texts.TEXTS}
    assert not missing, missing
    assert {"mode_mentor", "mode_coding_partner", "mode_other"} <= set(chat_texts.TEXTS)
    # What the chat says lives in chat_texts; app.py keeps only the "done" words students type.
    lines = [ln for ln in source.splitlines() if _HEBREW.search(ln) and "_DONE_TEXT" not in ln and "_HEBREW" not in ln]
    assert not lines, lines


def test_the_my_work_button_has_the_same_names_in_the_script():
    """public/reins-chat.js sends the "My work" command on one click: it finds
    the button by the command's names, in both languages."""
    js = (ROOT / "public" / "reins-chat.js").read_text(encoding="utf-8")
    he, en = chat_texts.TEXTS["cmd_my_work"]
    assert f'const MY_WORK = ["{en}", "{he}"];' in js


def _chat_app():
    """student_app/app.py, loaded by its path as Chainlit loads it."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("reins_student_chat", ROOT / "student_app" / "app.py")
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    return app


def _with_session(app, monkeypatch, cookie="", accept="", lab_lang=None):
    """Stand in for Chainlit's connection: its cookies, the browser's first
    language, and the lab's language once a lab is open."""
    from types import SimpleNamespace
    session = SimpleNamespace(environ={"HTTP_COOKIE": cookie} if cookie else {}, language=accept)
    store = {"lang": lab_lang}
    monkeypatch.setattr(app, "cl", SimpleNamespace(
        context=SimpleNamespace(session=session),
        user_session=SimpleNamespace(get=lambda k, d=None: store.get(k, d)),
    ))


def test_the_students_switch_picks_the_chats_language(monkeypatch):
    app = _chat_app()
    monkeypatch.delenv("CHAT_LANGUAGE", raising=False)
    # Nothing chosen: the browser's first language, then the lab's.
    _with_session(app, monkeypatch, accept="he-IL")
    assert app._lang() == "he"
    _with_session(app, monkeypatch, accept="en-US")
    assert app._lang() == "en"
    _with_session(app, monkeypatch, accept="en-US", lab_lang="he")
    assert app._lang() == "he"
    # The student's choice (the EN/עב switch's cookie) wins over both.
    _with_session(app, monkeypatch, cookie="other=1; reins_lang=en", accept="he-IL", lab_lang="he")
    assert app._lang() == "en"
    _with_session(app, monkeypatch, cookie="reins_lang=he", accept="en-US", lab_lang="en")
    assert app._lang() == "he"
    # A cookie that isn't one of the two languages counts as no choice.
    _with_session(app, monkeypatch, cookie="reins_lang=fr", accept="en-US")
    assert app._lang() == "en"
    # The lecturer's fixed language wins over the student's choice.
    monkeypatch.setenv("CHAT_LANGUAGE", "he")
    _with_session(app, monkeypatch, cookie="reins_lang=en", accept="en-US")
    assert app._lang() == "he"


def test_a_pass_brings_the_sign_in_back_once(monkeypatch):
    """The language switch's reload: the pass the page brings back in its
    cookie stands for the sign-in and the lab, once, and not after its minute."""
    app = _chat_app()
    keep = {"login": {"token": "t"}, "course_id": "c", "exercise_id": "e"}
    ticket = app._issue_pass(keep)
    _with_session(app, monkeypatch, cookie=f"reins_lang=en; {app.PASS_COOKIE}={ticket}")
    assert app._take_pass() == keep
    assert app._take_pass() is None  # used up
    # Out of time, unknown, or no cookie at all: sign in as usual.
    late = app._issue_pass(keep)
    app._passes[late]["until"] -= app.PASS_SECONDS + 1
    _with_session(app, monkeypatch, cookie=f"{app.PASS_COOKIE}={late}")
    assert app._take_pass() is None
    _with_session(app, monkeypatch, cookie=f"{app.PASS_COOKIE}=made-up")
    assert app._take_pass() is None
    _with_session(app, monkeypatch)
    assert app._take_pass() is None


def test_the_page_gets_a_pass_only_when_asked_and_signed_in(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    app = _chat_app()
    sent = []

    async def send_window_message(data):
        sent.append(data)

    def chat(keep):
        store = {"keep": keep}
        monkeypatch.setattr(app, "cl", SimpleNamespace(
            user_session=SimpleNamespace(get=lambda k, d=None: store.get(k, d)),
            send_window_message=send_window_message,
        ))

    keep = {"login": {"token": "t"}, "course_id": "c", "exercise_id": "e"}
    chat(keep)
    # Chainlit hands over every window message, its own replies too: no answer to those.
    for other in ("hello", {"reins": "resume-pass-for", "pass": "x"}, {"type": "x"}, None):
        asyncio.run(app.on_window_message(other))
    assert sent == []
    asyncio.run(app.on_window_message({"reins": "resume-pass", "id": "abc"}))
    assert sent[-1]["reins"] == "resume-pass-for" and sent[-1]["id"] == "abc"
    assert app._passes[sent[-1]["pass"]]["keep"] == keep
    # Not signed in yet: an empty answer, so the page just reloads.
    chat(None)
    asyncio.run(app.on_window_message({"reins": "resume-pass", "id": "def"}))
    assert sent[-1] == {"reins": "resume-pass-for", "id": "def", "pass": ""}


def test_the_page_and_the_chat_use_the_same_names_for_the_pass():
    js = (ROOT / "public" / "reins-chat.js").read_text(encoding="utf-8")
    app = _chat_app()
    assert f'const PASS_COOKIE = "{app.PASS_COOKIE}";' in js
    assert 'reins: "resume-pass", id' in js and 'd.reins !== "resume-pass-for"' in js
    assert "max-age=60;" in js and app.PASS_SECONDS == 60
