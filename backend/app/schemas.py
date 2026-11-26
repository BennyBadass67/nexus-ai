from typing import Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    model: str = Field(min_length=1)
    conversation_id: Optional[int] = None
    regenerate: bool = False
    project_id: Optional[int] = None
    images: Optional[list[str]] = None


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class SettingIn(BaseModel):
    value: str


class PullRequest(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z0-9._/-]+(:[A-Za-z0-9._-]+)?$", max_length=120)


class BenchRequest(BaseModel):
    model: str = Field(pattern=r"^[A-Za-z0-9._/-]+(:[A-Za-z0-9._-]+)?$", max_length=120)
