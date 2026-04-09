
import pytest

def test_security_headers_present(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert "geolocation=()" in r.headers["Permissions-Policy"]
