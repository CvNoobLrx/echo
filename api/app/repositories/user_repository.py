"""用户数据访问层。"""
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_model import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_login(self, email: str) -> User | None:
        normalized = email.strip().lower()
        result = await self.session.execute(
            select(User).where(
                or_(
                    func.lower(User.email) == normalized,
                    func.lower(User.username) == normalized,
                )
            )
        )
        return result.scalars().first()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, username: str, password_hash: str, *, email: str | None = None) -> User:
        user = User(username=username, email=email, password_hash=password_hash)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_password(self, user: User, password_hash: str) -> User:
        user.password_hash = password_hash
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_avatar(self, user: User, avatar: str) -> User:
        user.avatar = avatar
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_nickname(self, user: User, nickname: str) -> User:
        user.nickname = nickname
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_profile(
        self,
        user: User,
        *,
        username: str | object = ...,
        nickname: str | None | object = ...,
        email: str | None | object = ...,
    ) -> User:
        if username is not ...:
            user.username = username  # type: ignore[assignment]
        if nickname is not ...:
            user.nickname = nickname  # type: ignore[assignment]
        if email is not ...:
            user.email = email  # type: ignore[assignment]
        await self.session.commit()
        await self.session.refresh(user)
        return user
