"""The student's own copy of a session, to download and keep: "my work".

One self-contained HTML page (it opens in any browser, prints, and keeps Hebrew
right to left) with the lab's title, the course, the dates, how far the student
got (the steps of a class-paced lab, done or not), and then everything the
student's chat showed and everything the student wrote, in order: the brief,
each step, the outputs they pasted, the tutor's answers, the quiz questions and
their answers, and the lecturer's notes (backend/transcript.py).

An exercise that keeps no transcript (exercise.yaml `chat_history: false`) gets
what the server keeps elsewhere instead, also in order: the outputs they sent
for each step, the questions they answered, and their questions to the tutor.

Only what the student saw or wrote: nothing about other students, and no grade
or note of the lecturer's that their chat didn't show them. The student chat
offers it at the end of a lab and at any time (student_app/app.py);
GET /api/my-work/{session_id} (routes/my_work.py).
"""
import datetime
import html
import re
from typing import Any, Optional

from backend import courses, db, exercises, pacing, steps, transcript

try:  # installed with the tutor's libraries (rich); without it the text stays plain
    from markdown_it import MarkdownIt
except ImportError:  # pragma: no cover
    MarkdownIt = None

# The page's own words. The lab's text, the tutor's answers and the student's
# messages come as written.
_WORDS: dict[str, tuple[str, str]] = {
    "title": ("העבודה שלי", "My work"),
    "steps": ("השלבים", "The steps"),
    "done_of": ("סיימתם {done} מתוך {total} שלבים.", "You finished {done} of {total} steps."),
    "all_done": ("סיימתם את כל {total} השלבים. 🎉", "You finished all {total} steps. 🎉"),
    "log": ("המעבדה, לפי הסדר", "The lab, in order"),
    "log_plain": ("מה ששלחתם, לפי הסדר", "What you sent, in order"),
    "me": ("אני", "Me"),
    "tutor": ("REINS Edu", "REINS Edu"),
    "note": ("הודעה", "Note"),
    "my_output": ("הפלט שלי · שלב {label}", "My output · step {label}"),
    "question": ("שאלה", "Question"),
    "my_answer": ("התשובה שלי", "My answer"),
    "empty": ("עוד אין כאן כלום: המעבדה רק התחילה.", "Nothing here yet: the lab has only just started."),
    "saved": ("נשמר מ־REINS Edu ב־{when}.", "Saved from REINS Edu on {when}."),
    "step": ("שלב", "Step"),
}


def _w(key: str, lang: str, **values) -> str:
    he, en = _WORDS[key]
    s = he if lang == "he" else en
    return s.format(**values) if values else s


# --- Markdown -----------------------------------------------------------------------------

def _renderer(breaks: bool):
    if MarkdownIt is None:
        return None
    # No raw HTML: whatever anyone wrote is shown, never run.
    return MarkdownIt("commonmark", {"html": False, "breaks": breaks}).enable(["table", "strikethrough"])


_MD = _renderer(False)
_MD_TYPED = _renderer(True)  # the student's own messages: a new line is a new line
# Each paragraph, heading, list and quote takes its direction from its own text
# (Hebrew right to left, English left to right), as in the chat.
_BLOCKS = re.compile(r"<(p|li|ul|ol|h[1-6]|blockquote|td|th)>")


def _md(text: str, typed: bool = False) -> str:
    md = _MD_TYPED if typed else _MD
    if md is None:
        return f'<div class="plain" dir="auto">{html.escape(text or "")}</div>'
    return _BLOCKS.sub(r'<\1 dir="auto">', md.render(text or ""))


def _pre(text: str) -> str:
    return f'<pre class="output">{html.escape(text or "")}</pre>'


# --- times ------------------------------------------------------------------------------

def _local(value: Optional[str]) -> Optional[datetime.datetime]:
    """A database time (UTC) in the class's time zone (the server's)."""
    try:
        t = datetime.datetime.fromisoformat(str(value).replace("Z", ""))
    except ValueError:
        return None
    return t.replace(tzinfo=datetime.timezone.utc).astimezone()


def _hm(value: Optional[str]) -> str:
    t = _local(value)
    return t.strftime("%H:%M") if t else ""


def _day(t: Optional[datetime.datetime]) -> str:
    return t.strftime("%d.%m.%Y") if t else ""


# --- the page -----------------------------------------------------------------------------

def _entry(cls: str, who: str, when: str, body: str) -> str:
    head = f'<p class="who"><b>{html.escape(who)}</b>'
    head += f' <time>{html.escape(when)}</time></p>' if when else "</p>"
    return f'<article class="entry {cls}">{head}{body}</article>'


def _labels(ex: Optional[dict[str, Any]]) -> dict[int, str]:
    return {n: pacing.label(ex, n) for n in range(1, len(steps.steps_of(ex)) + 1)} if ex else {}


def _from_transcript(rows: list[dict[str, Any]], ex: Optional[dict[str, Any]], lang: str) -> list[str]:
    labels = _labels(ex)
    out = []
    for e in rows:
        when = _hm(e["created_at"])
        if e["author"] == "student":
            if e["kind"] == "output":
                label = labels.get(e["step"], str(e["step"] or ""))
                out.append(_entry("entry--me", _w("my_output", lang, label=label), when, _pre(e["content"])))
            else:
                out.append(_entry("entry--me", _w("me", lang), when, _md(e["content"], typed=True)))
        elif e["author"] == "system":
            out.append(_entry("entry--note", _w("note", lang), when, _md(e["content"])))
        else:
            cls = {"step": "entry--step", "brief": "entry--brief"}.get(e["kind"], "entry--tutor")
            out.append(_entry(cls, _w("tutor", lang), when, _md(e["content"])))
    return out


def _from_records(session_id: str, ex: Optional[dict[str, Any]], lang: str) -> list[str]:
    """No transcript: the outputs sent per step, the questions answered and the
    questions to the tutor, by time."""
    labels = _labels(ex)
    items: list[tuple[str, str]] = []
    with db.conn() as c:
        for r in c.execute("SELECT step, answer, created_at FROM step_checks WHERE session_id = ? "
                           "AND answer != '' ORDER BY id", (session_id,)):
            label = labels.get(r["step"], str(r["step"]))
            items.append((r["created_at"], _entry("entry--me", _w("my_output", lang, label=label),
                                                  _hm(r["created_at"]), _pre(r["answer"]))))
        for r in c.execute("SELECT body, answer, sent_at, answered_at FROM probes WHERE session_id = ? "
                           "AND answer IS NOT NULL ORDER BY id", (session_id,)):
            items.append((r["sent_at"], _entry("entry--tutor", _w("question", lang), _hm(r["sent_at"]),
                                               _md(r["body"]))))
            items.append((r["answered_at"] or r["sent_at"],
                          _entry("entry--me", _w("my_answer", lang), _hm(r["answered_at"]),
                                 _md(r["answer"], typed=True))))
        for r in c.execute("SELECT role, body, created_at FROM messages WHERE session_id = ? ORDER BY id",
                           (session_id,)):
            mine = r["role"] == "user"
            items.append((r["created_at"], _entry("entry--me" if mine else "entry--tutor",
                                                  _w("me" if mine else "tutor", lang), _hm(r["created_at"]),
                                                  _md(r["body"], typed=mine))))
    items.sort(key=lambda it: it[0] or "")
    return [h for _, h in items]


def _progress(session_id: str, ex: dict[str, Any], lang: str) -> str:
    total = pacing.total(ex)
    if not total:
        return ""
    cur = steps.current_step(session_id)
    done = min(cur - 1, total)
    lines = []
    for n, st in enumerate(steps.steps_of(ex), start=1):
        mark, cls = ("✅", "done") if n < cur else (("▶️", "now") if n == cur else ("⬜", "later"))
        lines.append(f'<li class="{cls}" dir="auto">{mark} {html.escape(_w("step", lang))} '
                     f'{html.escape(pacing.label(ex, n))} · {html.escape(str(st.get("title") or ""))}</li>')
    said = _w("all_done", lang, total=total) if done >= total else _w("done_of", lang, done=done, total=total)
    return (f'<section class="progress"><h2>{_w("steps", lang)}</h2><p>{html.escape(said)}</p>'
            f'<ul class="steps">{"".join(lines)}</ul></section>')


_CSS = """
:root { color-scheme: light; --ink: #1d2227; --muted: #5a6470; --line: #d9dee3; --primary: #0b6a87;
  --me: #e6f2f6; --note: #fff6dc; }
* { box-sizing: border-box; }
body { margin: 0; background: #eef1f3; color: var(--ink); line-height: 1.55; font-size: 16px;
  font-family: Assistant, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, "Noto Sans Hebrew",
  "Arial Hebrew", sans-serif; }
header { background: var(--ink); color: #eef0f2; padding: 22px 24px 18px; }
header .brand { margin: 0 0 4px; font-size: 13px; letter-spacing: .08em; text-transform: uppercase; color: #f2b705; }
header h1 { margin: 0; font-size: 26px; line-height: 1.25; }
header .meta { margin: 6px 0 0; color: #c4cbd2; font-size: 15px; }
main { max-width: 860px; margin: 0 auto; padding: 20px 16px 8px; }
h2 { font-size: 19px; margin: 22px 0 10px; }
.progress p { margin: 0 0 8px; }
.steps { list-style: none; margin: 0; padding: 0; }
.steps li { padding: 3px 0; }
.steps li.later { color: var(--muted); }
.steps li.now { font-weight: 700; }
.entry { background: #fff; border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px; margin: 10px 0; }
.entry--me { background: var(--me); border-color: #bcdbe6; }
.entry--note { background: var(--note); border-color: #ecd9a0; }
.entry--step, .entry--brief { border-inline-start: 4px solid var(--primary); }
.who { margin: 0 0 4px; font-size: 13px; color: var(--muted); }
.who b { color: var(--ink); }
.who b, .who time { unicode-bidi: isolate; }
.who time { margin-inline-start: 6px; }
.entry > :last-child { margin-bottom: 0; }
.entry h1, .entry h2, .entry h3, .entry h4 { margin: 6px 0; font-size: 18px; }
[dir] { text-align: start; }
pre, code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13.5px; }
pre { direction: ltr; text-align: left; unicode-bidi: isolate; background: #f4f6f8; border: 1px solid var(--line);
  border-radius: 6px; padding: 10px 12px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
pre.output { background: #1d2227; color: #e8ecef; border-color: #1d2227; }
:not(pre) > code { direction: ltr; unicode-bidi: isolate; background: #eef1f3; padding: 1px 4px; border-radius: 4px; }
table { border-collapse: collapse; } td, th { border: 1px solid var(--line); padding: 4px 8px; }
blockquote { margin: 6px 0; padding: 2px 12px; border-inline-start: 3px solid var(--line); color: var(--muted); }
.plain { white-space: pre-wrap; }
footer { max-width: 860px; margin: 0 auto; padding: 8px 16px 28px; color: var(--muted); font-size: 13px; }
@media print { body { background: #fff; } header { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .entry { break-inside: avoid; } }
"""


def page(session_id: str, lang: Optional[str] = None) -> tuple[str, str]:
    """The page for one session and its file name. `lang` 'he' or 'en' for the
    page's own words; None = the lab's language."""
    with db.conn() as c:
        s = c.execute(
            "SELECT s.id, s.exercise, s.course_id, s.started_at, s.last_active_at, u.username "
            "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id = ?", (session_id,)).fetchone()
    if s is None:
        raise KeyError(session_id)
    try:
        ex = exercises.get(s["exercise"])
    except KeyError:  # removed since; the record stays
        ex = None
    if lang not in ("he", "en"):
        lang = "he" if ex and pacing.hebrew(ex) else "en"
    title = ((ex.get("title_he") or ex.get("title_en")) if lang == "he" else ex.get("title_en")) if ex else None
    title = title or s["exercise"]
    course = courses.get(s["course_id"]) if s["course_id"] else None

    rows = transcript.entries(session_id, limit=1_000_000)["entries"] if transcript.enabled(ex) else []
    if rows:
        body, heading = _from_transcript(rows, ex, lang), _w("log", lang)
    else:
        body, heading = _from_records(session_id, ex, lang), _w("log_plain", lang)

    first, last = _local(s["started_at"]), _local(s["last_active_at"])
    days = _day(first) if _day(first) == _day(last) else f"{_day(first)} – {_day(last)}"
    meta = " · ".join(html.escape(x) for x in (course["name"] if course else "", s["username"], days) if x)
    now = datetime.datetime.now().astimezone()
    saved = _w("saved", lang, when=now.strftime("%d.%m.%Y %H:%M"))
    heading_html = f"{html.escape(_w('title', lang))}: {html.escape(title)}"

    doc = (
        f'<!doctype html>\n<html lang="{lang}" dir="{"rtl" if lang == "he" else "ltr"}">\n<head>\n'
        '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{heading_html}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n"
        f'<header><p class="brand">REINS Edu</p><h1 dir="auto">{heading_html}</h1>'
        f'<p class="meta" dir="auto">{meta}</p></header>\n<main>\n'
        f'{_progress(session_id, ex, lang) if ex else ""}\n'
        f'<section class="log"><h2>{html.escape(heading)}</h2>\n'
        + ("\n".join(body) if body else f"<p>{html.escape(_w('empty', lang))}</p>")
        + f"\n</section>\n</main>\n<footer>{html.escape(saved)}</footer>\n</body>\n</html>\n"
    )
    name = f"my-work-{re.sub(r'[^A-Za-z0-9._-]', '-', s['exercise'])}-{now.strftime('%Y-%m-%d')}.html"
    return doc, name
