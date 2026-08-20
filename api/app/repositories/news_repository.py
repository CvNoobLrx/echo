"""Persistence for news subscriptions and delivery audit records."""
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news_delivery_model import NewsDelivery
from app.models.news_subscription_model import NewsSubscription


class NewsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_subscription(self, user_id: uuid.UUID) -> NewsSubscription | None:
        result = await self.session.execute(
            select(NewsSubscription).where(NewsSubscription.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def save_subscription(
        self, user_id: uuid.UUID, *, enabled: bool, topics: list[str]
    ) -> NewsSubscription:
        subscription = await self.get_subscription(user_id)
        if subscription is None:
            subscription = NewsSubscription(user_id=user_id)
            self.session.add(subscription)
        subscription.enabled = enabled
        subscription.topics = topics
        await self.session.commit()
        await self.session.refresh(subscription)
        return subscription

    async def save_smtp(
        self,
        user_id: uuid.UUID,
        *,
        provider: str,
        username: str,
        password_encrypted: str | None,
        from_name: str,
    ) -> NewsSubscription:
        subscription = await self.get_subscription(user_id)
        if subscription is None:
            subscription = NewsSubscription(user_id=user_id, enabled=False, topics=[])
            self.session.add(subscription)
        subscription.smtp_provider = provider
        subscription.smtp_username = username
        if password_encrypted is not None:
            subscription.smtp_password_encrypted = password_encrypted
        subscription.smtp_from_name = from_name
        await self.session.commit()
        await self.session.refresh(subscription)
        return subscription

    async def list_enabled(self) -> list[NewsSubscription]:
        result = await self.session.execute(
            select(NewsSubscription).where(NewsSubscription.enabled.is_(True))
        )
        return list(result.scalars().all())

    async def create_delivery(self, delivery: NewsDelivery) -> NewsDelivery | None:
        self.session.add(delivery)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return None
        await self.session.refresh(delivery)
        return delivery

    async def get_delivery(
        self, user_id: uuid.UUID, delivery_id: uuid.UUID
    ) -> NewsDelivery | None:
        result = await self.session.execute(
            select(NewsDelivery).where(
                NewsDelivery.id == delivery_id, NewsDelivery.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def get_delivery_by_id(self, delivery_id: uuid.UUID) -> NewsDelivery | None:
        return await self.session.get(NewsDelivery, delivery_id)

    async def latest_delivery(self, user_id: uuid.UUID) -> NewsDelivery | None:
        result = await self.session.execute(
            select(NewsDelivery)
            .where(NewsDelivery.user_id == user_id)
            .order_by(NewsDelivery.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def save_delivery(self, delivery: NewsDelivery) -> NewsDelivery:
        await self.session.commit()
        await self.session.refresh(delivery)
        return delivery
