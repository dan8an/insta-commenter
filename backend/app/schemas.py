from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal
from .services.post_resolver import normalize_url

class Target(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    url: str = Field(max_length=2048)
    @field_validator('url')
    @classmethod
    def valid_url(cls, value): return normalize_url(value)
class Publish(Target):
    message: str = Field(min_length=1, max_length=2200)
    operation: Literal['comment', 'reply'] = 'comment'
    parent_comment_id: str | None = Field(default=None, pattern=r'^\d{1,64}$')
    @field_validator('message')
    @classmethod
    def text(cls, value):
        if not value.strip(): raise ValueError('Write a comment first.')
        return value
