"""按需生成每日回顾；不依赖 Celery Beat。"""

import uuid
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.conversation_model import ROLE_USER, Conversation, Message
from app.models.daily_review_model import DailyReview
from app.models.document_model import Document
from app.models.memory_model import MEMORY_STATUS_DONE, Memory

logger = get_logger(__name__)


class DailyReviewService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _range(day: date) -> tuple[datetime, datetime]:
        return datetime.combine(day, time.min), datetime.combine(day, time.max)

    @staticmethod
    def _stats(data: dict) -> dict[str, int]:
        return {
            "messages": len(data["messages"]),
            "memories": len(data["memories"]),
            "documents": len(data["documents"]),
        }

    async def collect(self, user_id: uuid.UUID, day: date) -> dict:
        start, end = self._range(day)
        message_rows = await self.session.execute(
            select(Message.content)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Message.role == ROLE_USER,
                Message.created_at >= start,
                Message.created_at <= end,
                Conversation.user_id == user_id,
            )
            .limit(30)
        )
        memory_rows = await self.session.execute(
            select(Memory.raw_text).where(
                Memory.user_id == user_id,
                Memory.status == MEMORY_STATUS_DONE,
                Memory.created_at >= start,
                Memory.created_at <= end,
            )
        )
        document_rows = await self.session.execute(
            select(Document.file_name).where(
                Document.user_id == user_id,
                Document.created_at >= start,
                Document.created_at <= end,
            )
        )
        return {
            "messages": [row[0] for row in message_rows.all()],
            "memories": [row[0] for row in memory_rows.all()],
            "documents": [row[0] for row in document_rows.all()],
        }

    @staticmethod
    def instant_content(data: dict) -> str:
        stats = DailyReviewService._stats(data)
        if sum(stats.values()) == 0:
            return "今天还没有新动态，休息一下也很好。"
        return (
            f"今天有 {stats['messages']} 次提问，记住了 {stats['memories']} 件事，"
            f"新增了 {stats['documents']} 份文档。"
        )

    async def _get(self, user_id: uuid.UUID, day: date) -> DailyReview | None:
        return await self.session.scalar(
            select(DailyReview).where(
                DailyReview.user_id == user_id,
                DailyReview.review_date == day,
            )
        )

    async def get_or_create(
        self, user_id: uuid.UUID, day: date | None = None
    ) -> dict:
        day = day or date.today()
        data = await self.collect(user_id, day)
        stats = self._stats(data)
        review = await self._get(user_id, day)

        if review and review.stats == stats and review.content:
            return self.to_dict(review)

        if review is None:
            review = DailyReview(
                user_id=user_id,
                review_date=day,
                content=self.instant_content(data),
                care="要不要聊聊今天的进展？" if sum(stats.values()) else None,
                stats=stats,
                status="ready",
            )
            self.session.add(review)
        else:
            review.content = self.instant_content(data)
            review.care = "要不要聊聊今天的进展？" if sum(stats.values()) else None
            review.stats = stats
            review.status = "ready"
            review.error_message = None
        await self.session.commit()
        await self.session.refresh(review)

        if sum(stats.values()):
            await self._enqueue(review)
        return self.to_dict(review)

    async def request_regeneration(
        self, user_id: uuid.UUID, day: date | None = None
    ) -> dict:
        day = day or date.today()
        review = await self._get(user_id, day)
        if review is None:
            await self.get_or_create(user_id, day)
            review = await self._get(user_id, day)
        if review is None:
            raise RuntimeError("每日回顾创建失败")
        if review.status != "generating":
            await self._enqueue(review)
        return self.to_dict(review)

    async def _enqueue(self, review: DailyReview) -> None:
        review.status = "generating"
        review.error_message = None
        await self.session.commit()
        try:
            from app.tasks.daily_review import generate_daily_review_task

            generate_daily_review_task.delay(
                str(review.user_id), review.review_date.isoformat()
            )
        except Exception as exc:
            logger.warning("每日回顾任务投递失败: %s", exc)
            review.status = "ready"
            review.error_message = str(exc)[:500]
            await self.session.commit()

    async def regenerate(
        self, user_id: uuid.UUID, day: date | None = None
    ) -> dict:
        day = day or date.today()
        data = await self.collect(user_id, day)
        stats = self._stats(data)
        review = await self._get(user_id, day)
        if review is None:
            review = DailyReview(
                user_id=user_id,
                review_date=day,
                content=self.instant_content(data),
                stats=stats,
            )
            self.session.add(review)

        fallback = self.instant_content(data)
        content = fallback
        care = "今天有一些新的进展，要不要聊聊？" if sum(stats.values()) else None
        if sum(stats.values()):
            try:
                from app.core.llm.resolver import get_optional_client_for_type

                client = await get_optional_client_for_type(
                    self.session, user_id, "chat"
                )
                if client:
                    prompt = (
                        "请为用户生成简洁自然的今日回顾，最多120字，不添加未提供的事实。"
                        f"\n今日提问：{'；'.join(data['messages'][:10]) or '无'}"
                        f"\n新增记忆：{'；'.join(data['memories'][:10]) or '无'}"
                        f"\n新增文档：{'、'.join(data['documents'][:10]) or '无'}"
                    )
                    generated = await client.chat(
                        [{"role": "user", "content": prompt}],
                        temperature=0.5,
                        max_tokens=300,
                    )
                    content = generated.strip() or fallback
                    care_prompt = (
                        "基于以下今日回顾，写一句自然克制、可用于开启对话的关心或追问，"
                        "最多40字：\n" + content
                    )
                    generated_care = await client.chat(
                        [{"role": "user", "content": care_prompt}],
                        temperature=0.6,
                        max_tokens=100,
                    )
                    care = generated_care.strip().strip('\"「」') or care
            except Exception as exc:
                logger.warning("每日回顾模型润色失败，使用统计文案: %s", exc)

        review.content = content
        review.stats = stats
        review.care = care
        review.status = "ready"
        review.error_message = None
        await self.session.commit()
        await self.session.refresh(review)
        return self.to_dict(review)

    @staticmethod
    def to_dict(review: DailyReview) -> dict:
        return {
            "date": review.review_date.isoformat(),
            "content": review.content,
            "care": review.care or "",
            "stats": review.stats or {},
            "status": review.status,
            "created_at": review.created_at.isoformat() if review.created_at else None,
        }
