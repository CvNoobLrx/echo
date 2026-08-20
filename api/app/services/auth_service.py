"""鉴权业务服务：注册、登录、刷新、改密、头像。"""
import re
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.storage import build_file_key, get_storage
from app.models.user_model import User
from app.repositories.user_repository import UserRepository

logger = get_logger(__name__)

_AVATAR_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_AVATAR_MAX = 5 * 1024 * 1024  # 5MB
_EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
)


def _normalize_email(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if not normalized or not _EMAIL_PATTERN.fullmatch(normalized):
        raise BizError("请输入有效的邮箱地址", code=1010)
    return normalized


class AuthService:
    def __init__(self, session: AsyncSession):
        self.repo = UserRepository(session)

    async def register(self, username: str, password: str) -> User:
        email = _normalize_email(username)
        if await self.repo.get_by_login(email):
            logger.warning("注册失败，邮箱已存在: %s", email)
            raise BizError("邮箱已被注册", code=1001, status_code=409)
        user = await self.repo.create(email, hash_password(password), email=email)
        logger.info("用户注册成功: email=%s id=%s", email, user.id)
        return user

    async def authenticate(self, username: str, password: str) -> User:
        email = username.strip().lower()
        user = await self.repo.get_by_login(email)
        if not user or not verify_password(password, user.password_hash):
            logger.warning("登录失败，邮箱或密码错误: %s", email)
            raise BizError("邮箱或密码错误", code=1002, status_code=401)
        logger.info("用户登录成功: email=%s id=%s", email, user.id)
        return user

    def issue_tokens(self, user: User) -> tuple[str, str]:
        sub = str(user.id)
        return create_access_token(sub), create_refresh_token(sub)

    async def refresh(self, refresh_token: str) -> tuple[str, str]:
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise BizError("刷新令牌无效", code=1003, status_code=401)
        user = await self.repo.get_by_id(uuid.UUID(payload["sub"]))
        if not user:
            raise BizError("用户不存在", code=1004, status_code=401)
        return self.issue_tokens(user)

    async def change_password(
        self, user: User, old_password: str, new_password: str
    ) -> None:
        if not verify_password(old_password, user.password_hash):
            logger.warning("改密失败，原密码错误: id=%s", user.id)
            raise BizError("原密码错误", code=1005, status_code=400)
        await self.repo.update_password(user, hash_password(new_password))
        logger.info("用户修改密码成功: id=%s", user.id)

    async def update_avatar(self, user: User, file_name: str, content: bytes) -> User:
        """上传头像：校验 → 存对象存储 → 回写 file_key。"""
        ext = Path(file_name).suffix.lower()
        if ext not in _AVATAR_EXTS:
            raise BizError(f"不支持的图片类型: {ext}", code=1006)
        if len(content) > _AVATAR_MAX:
            raise BizError("头像超过 5MB 限制", code=1007)
        file_key = build_file_key(str(user.id), "avatars", uuid.uuid4().hex, ext)
        await get_storage().save(file_key, content)
        updated = await self.repo.update_avatar(user, file_key)
        logger.info("用户更新头像: id=%s key=%s", user.id, file_key)
        return updated

    async def update_nickname(self, user: User, nickname: str) -> User:
        """更新昵称。"""
        name = (nickname or "").strip()
        if not name:
            raise BizError("昵称不能为空", code=1008)
        updated = await self.repo.update_nickname(user, name)
        logger.info("用户更新昵称: id=%s", user.id)
        return updated

    async def update_profile(
        self,
        user: User,
        *,
        nickname: str | None,
        email: str | None,
        fields_set: set[str],
    ) -> User:
        """Partially update nickname and account email."""
        if not fields_set:
            raise BizError("没有需要更新的资料", code=1009)

        nickname_value: str | None | object = ...
        email_value: str | None | object = ...
        username_value: str | object = ...
        if "nickname" in fields_set:
            name = (nickname or "").strip()
            if not name:
                raise BizError("昵称不能为空", code=1008)
            nickname_value = name
        if "email" in fields_set:
            normalized = (email or "").strip().lower()
            if normalized:
                normalized = _normalize_email(normalized)
                existing = await self.repo.get_by_login(normalized)
                if existing is not None and existing.id != user.id:
                    raise BizError("该邮箱已被其他账号使用", code=1011, status_code=409)
                username_value = normalized
            email_value = normalized or None

        updated = await self.repo.update_profile(
            user,
            username=username_value,
            nickname=nickname_value,
            email=email_value,
        )
        logger.info("用户更新资料: id=%s fields=%s", user.id, sorted(fields_set))
        return updated
