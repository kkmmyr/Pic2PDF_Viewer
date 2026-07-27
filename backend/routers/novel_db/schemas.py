"""novel_db ルーター共通 Pydantic スキーマ。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ScopeModel(BaseModel):
    type: Literal["all", "series", "book"]
    id: str | None = None


class RebuildRequest(BaseModel):
    type: Literal["book", "series", "all"]
    target_id: str | None = None
    mode: Literal[
        "rebuild",
        "ocr",
        "full_build",
        "generate_contexts",
        "generate_relations",
    ] = Field(default="rebuild")


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    scope: ScopeModel
    offset: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=50)


class QaRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    scope: ScopeModel


class ChatSessionStartRequest(BaseModel):
    scope: ScopeModel
    question: str = Field(..., min_length=1, max_length=500)


class ChatSessionContinueRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


class ChatSessionTitleUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("title is required")
        return title


class ChatMessagePayload(BaseModel):
    id: int
    role: Literal["user", "assistant", "system"]
    content: str
    eval_count: int | None
    done_reason: str | None
    created_at: str


class ChatSessionSummary(BaseModel):
    id: int
    scope_type: Literal["all", "series", "book"]
    scope_id: str | None
    title: str | None
    started_at: str
    last_message_at: str | None
    message_count: int


class ChatSessionDetailPayload(BaseModel):
    id: int
    scope_type: Literal["all", "series", "book"]
    scope_id: str | None
    title: str | None
    started_at: str
    last_message_at: str | None
    messages: list[ChatMessagePayload]


class CharacterSummary(BaseModel):
    name: str
    first_page: int
    page_count: int
    has_summary: bool


class CharacterScene(BaseModel):
    page_no: int
    char_count: int


class CharacterDetail(BaseModel):
    name: str
    first_page: int
    page_count: int
    summary: str | None
    generated_at: str | None
    top_scenes: list[CharacterScene]
