"""Pydantic API contracts."""

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.routing.router import RouteLabel


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2_000)

    @field_validator("message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message must not be blank")
        return stripped


class SourceResponse(BaseModel):
    chunk_id: int
    source_file: str
    section_title: str
    content: str


class ChatResponse(BaseModel):
    answer: str
    route: RouteLabel | None
    sql: str | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[SourceResponse] = Field(default_factory=list)
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
