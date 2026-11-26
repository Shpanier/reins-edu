"""Other sites may not show REINS Edu's pages inside a frame (backend/main.py,
NoFramingByOtherSites): the student chat's language-switch pass travels by a
window message, which a framing page could ask for."""
from fastapi.testclient import TestClient

from backend.main import app


def test_pages_say_only_this_site_may_frame_them():
    with TestClient(app) as tc:
        for path in ("/healthz", "/api/login/methods"):
            r = tc.get(path)
            assert r.headers["content-security-policy"] == "frame-ancestors 'self'"
            assert r.headers["x-frame-options"] == "SAMEORIGIN"
