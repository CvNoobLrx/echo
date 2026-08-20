"""News subscription API schemas."""
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
)


class NewsSubscriptionUpdate(BaseModel):
    enabled: bool = False
    topics: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("topics")
    @classmethod
    def validate_topics(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            topic = (raw or "").strip()
            if not topic:
                continue
            if len(topic) > 30:
                raise ValueError("每个兴趣主题不能超过 30 个字符")
            key = topic.casefold()
            if key not in seen:
                normalized.append(topic)
                seen.add(key)
        if len(normalized) > 6:
            raise ValueError("最多设置 6 个兴趣主题")
        return normalized


class NewsSmtpUpdate(BaseModel):
    provider: Literal["qq", "163", "gmail", "outlook"]
    sender_email: str = Field(min_length=3, max_length=255)
    password: str | None = Field(default=None, max_length=512)
    from_name: str = Field(default="回声 Echo", min_length=1, max_length=128)

    @field_validator("sender_email")
    @classmethod
    def validate_sender_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("请输入有效的发件邮箱")
        return normalized

    @field_validator("password")
    @classmethod
    def normalize_password(cls, value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None

    @field_validator("from_name")
    @classmethod
    def normalize_from_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("请输入发件人名称")
        return normalized
