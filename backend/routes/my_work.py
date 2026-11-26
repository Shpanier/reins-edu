"""The student's own copy of a session, to download (backend/my_work.py):
one HTML page with the lab, how far they got, and the whole conversation.
Students get their own sessions; teachers any session."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from backend import deps, my_work

router = APIRouter()


@router.get("/my-work/{session_id}", response_class=HTMLResponse)
def download_my_work(session_id: str, lang: Optional[Literal["he", "en"]] = None,
                     user: dict = Depends(deps.current_user)):
    """lang: the page's own words in Hebrew or English (default: the lab's language)."""
    deps.require_owns_session(session_id, user)
    page, name = my_work.page(session_id, lang)
    return HTMLResponse(page, headers={"Content-Disposition": f'attachment; filename="{name}"',
                                       "Cache-Control": "no-store"})
