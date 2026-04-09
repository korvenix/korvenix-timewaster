from fastapi import FastAPI

from app.routes import config, join_events, meetings, reports, sync

app = FastAPI(
    title="Time Waster API",
    description="Backend for the Time Waster meeting cost tracking plugin",
    version="0.1.0",
)

app.include_router(config.router)
app.include_router(join_events.router)
app.include_router(meetings.router)
app.include_router(reports.router)
app.include_router(sync.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
