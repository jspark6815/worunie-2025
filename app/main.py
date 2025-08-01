from fastapi import FastAPI
from .events import router as slack_events_router

app = FastAPI(title="Slack Worunie Bot")

app.include_router(slack_events_router, prefix="/slack")
