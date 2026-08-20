"""News subscription settings and delivery endpoints."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.news_schema import NewsSmtpUpdate, NewsSubscriptionUpdate
from app.services.news_service import NewsService

router = APIRouter(tags=["news"])


@router.get("/news-subscription")
async def get_subscription(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await NewsService(session).get_settings(user))


@router.put("/news-subscription")
async def update_subscription(
    body: NewsSubscriptionUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await NewsService(session).update_settings(user, body), "设置已保存")


@router.post("/news-subscription/test-email")
async def test_email(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await NewsService(session).test_email(user)
    return success(message="测试邮件已发送")


@router.put("/news-subscription/smtp")
async def update_smtp(
    body: NewsSmtpUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await NewsService(session).update_smtp(user, body), "发件服务已保存")


@router.post("/news-subscription/send-now")
async def send_now(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    delivery = await NewsService(session).create_manual_delivery(user)
    from app.tasks.news import deliver_news_task

    deliver_news_task.delay(str(delivery.id))
    return success({"delivery_id": str(delivery.id)}, "晨报任务已提交")


@router.get("/news-deliveries/{delivery_id}")
async def get_delivery(
    delivery_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    delivery = await NewsService(session).repo.get_delivery(user.id, delivery_id)
    if delivery is None:
        from app.core.exceptions import BizError

        raise BizError("新闻发送记录不存在", code=3093, status_code=404)
    return success(NewsService.delivery_dict(delivery))
