from fastapi import FastAPI, Request

from app.routes import config, join_events, meetings, reports, sync

app = FastAPI(
    title="Time Waster API",
    description="Backend for the Time Waster meeting cost tracking plugin",
    version="0.1.0",
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none';"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


app.include_router(config.router)
app.include_router(join_events.router)
app.include_router(meetings.router)
app.include_router(reports.router)
app.include_router(sync.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
