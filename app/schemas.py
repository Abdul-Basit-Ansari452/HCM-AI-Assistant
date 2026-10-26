"""Pydantic v2 schemas shared across routes."""

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Response for the healthcheck endpoint."""

    status: str


class ORMModel(BaseModel):
    """Base schema for responses built from SQLAlchemy objects."""

    model_config = ConfigDict(from_attributes=True)
