from fastapi import FastAPI
from .events import router as slack_events_router
from .slash_commands import router as slash_commands_router

app = FastAPI(title="Slack Worunie Bot")

app.include_router(slack_events_router, prefix="/slack")
app.include_router(slash_commands_router, prefix="/slack")
