"""FastAPI application entrypoint."""

from fastapi import FastAPI

from miro.routers import health, platforms, publisher, renders
from miro.research import service as research_service
from miro.research.router import router as research_router

app = FastAPI(title="Miro API", version="0.1.0")
app.state.research_provider = research_service.NullProvider()

app.include_router(health.router)
app.include_router(renders.router)
app.include_router(publisher.router)
app.include_router(platforms.router)
app.include_router(research_router)
