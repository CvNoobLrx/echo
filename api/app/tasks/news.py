"""Celery tasks for the fixed daily news schedule."""
import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.celery_app import celery_app
from app.core.llm.client import close_llm_client
from app.db.postgres import create_task_engine
from app.services.news_service import NewsService


async def _with_service(callback):
    engine = create_task_engine()
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with maker() as session:
            return await callback(NewsService(session))
    finally:
        await engine.dispose()
        await close_llm_client()


@celery_app.task(name="app.tasks.news.dispatch_daily_news")
def dispatch_daily_news_task() -> int:
    async def run(service: NewsService):
        return await service.create_scheduled_deliveries()

    deliveries = asyncio.run(_with_service(run))
    for delivery in deliveries:
        deliver_news_task.delay(str(delivery.id))
    return len(deliveries)


@celery_app.task(
    bind=True,
    name="app.tasks.news.deliver_news",
    max_retries=2,
)
def deliver_news_task(self, delivery_id: str) -> str:
    async def run(service: NewsService):
        await service.run_delivery(uuid.UUID(delivery_id))

    try:
        asyncio.run(_with_service(run))
    except Exception as exc:
        failure = exc
        final = self.request.retries >= self.max_retries

        async def record_failure(service: NewsService):
            await service.record_delivery_failure(
                uuid.UUID(delivery_id), failure, final=final
            )

        asyncio.run(_with_service(record_failure))
        if final:
            raise
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
    return delivery_id
