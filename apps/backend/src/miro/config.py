"""Application settings."""

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "miro"
    debug: bool = False


settings = Settings()
