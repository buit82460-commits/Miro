"""FastAPI application entrypoint."""

from fastapi import FastAPI

from miro.routers import health, publisher, renders

app = FastAPI(title="Miro API", version="0.1.0")

app.include_router(health.router)
app.include_router(renders.router)
app.include_router(publisher.router)
