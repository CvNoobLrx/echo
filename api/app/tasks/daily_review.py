"""按需每日回顾的异步重生成任务；不配置 beat schedule。"""
import asyncio
import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.celery_app import celery_app
from app.core.llm.client import close_llm_client
from app.db.postgres import create_task_engine
from app.services.daily_review_service import DailyReviewService


async def _run(user_id: str, review_date: str) -> None:
    engine = create_task_engine()
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with maker() as session:
            await DailyReviewService(session).regenerate(
                uuid.UUID(user_id), date.fromisoformat(review_date)
            )
    finally:
        await engine.dispose()
        await close_llm_client()


@celery_app.task(name="app.tasks.daily_review.generate_daily_review")
def generate_daily_review_task(user_id: str, review_date: str) -> str:
    asyncio.run(_run(user_id, review_date))
    return user_id
