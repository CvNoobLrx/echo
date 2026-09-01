"""Daily news subscription, generation, and delivery workflow."""
import asyncio
import html
import json
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.research.retriever import get_websearch_config
from app.core.agent.tracing import get_tracer, push_llm_usage
from app.core.agent.web_search import web_search_structured
from app.core.exceptions import BizError
from app.core.llm.chat_model import build_default_chat_model
from app.core.llm.types import HumanMessage, SystemMessage
from app.core.logging import get_logger
from app.core.news.mailer import SmtpConfig, send_email
from app.core.security import decrypt_secret, encrypt_secret
from app.models.news_delivery_model import (
    STATUS_FAILED,
    STATUS_GENERATING,
    STATUS_QUEUED,
    STATUS_SENT,
    TRIGGER_MANUAL,
    TRIGGER_SCHEDULED,
    NewsDelivery,
)
from app.models.user_model import User
from app.repositories.model_config_repository import ModelConfigRepository
from app.repositories.news_repository import NewsRepository
from app.repositories.user_repository import UserRepository
from app.schemas.news_schema import NewsSmtpUpdate, NewsSubscriptionUpdate

logger = get_logger(__name__)
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
SMTP_PROVIDERS: dict[str, tuple[str, int, str]] = {
    "qq": ("smtp.qq.com", 465, "ssl"),
    "163": ("smtp.163.com", 465, "ssl"),
    "gmail": ("smtp.gmail.com", 465, "ssl"),
    "outlook": ("smtp.office365.com", 587, "starttls"),
}


class NewsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = NewsRepository(session)

    async def get_settings(self, user: User) -> dict:
        subscription = await self.repo.get_subscription(user.id)
        latest = await self.repo.latest_delivery(user.id)
        configs = ModelConfigRepository(self.session)
        chat_ready = bool(await configs.list_by_user(user.id, "chat"))
        search_ready = bool(await configs.list_by_user(user.id, "websearch"))
        smtp_configured = self._smtp_configured(subscription)
        return {
            "enabled": subscription.enabled if subscription else False,
            "topics": subscription.topics if subscription else [],
            "email": user.email,
            "schedule": "每天 08:00（北京时间）",
            "readiness": {
                "smtp": smtp_configured,
                "chat_model": chat_ready,
                "web_search": search_ready,
            },
            "smtp": {
                "configured": smtp_configured,
                "provider": subscription.smtp_provider if subscription else None,
                "sender_email": subscription.smtp_username if subscription else None,
                "from_name": subscription.smtp_from_name if subscription else None,
            },
            "latest_delivery": self.delivery_dict(latest) if latest else None,
        }

    async def update_settings(
        self, user: User, body: NewsSubscriptionUpdate
    ) -> dict:
        if body.enabled and not user.email:
            raise BizError("请先在个人资料中设置邮箱，再启用每日新闻推送", code=3090)
        current = await self.repo.get_subscription(user.id)
        if body.enabled and not self._smtp_configured(current):
            raise BizError("请先配置 SMTP 发件服务，再启用每日新闻推送", code=3096)
        await self.repo.save_subscription(
            user.id, enabled=body.enabled, topics=body.topics
        )
        return await self.get_settings(user)

    async def update_smtp(self, user: User, body: NewsSmtpUpdate) -> dict:
        current = await self.repo.get_subscription(user.id)
        credentials_changed = bool(
            current
            and (
                current.smtp_provider != body.provider
                or current.smtp_username != body.sender_email
            )
        )
        if body.password is None and (
            not current or not current.smtp_password_encrypted or credentials_changed
        ):
            raise BizError("请输入邮箱授权码或应用密码", code=3097)
        encrypted = encrypt_secret(body.password) if body.password else None
        await self.repo.save_smtp(
            user.id,
            provider=body.provider,
            username=body.sender_email,
            password_encrypted=encrypted,
            from_name=body.from_name,
        )
        return await self.get_settings(user)

    async def test_email(self, user: User) -> None:
        recipient = self._require_email(user)
        subscription = await self.repo.get_subscription(user.id)
        smtp_config = self._smtp_config(subscription)
        try:
            await send_email(
                recipient,
                "回声 Echo 新闻推送测试",
                "这是一封测试邮件。收到此邮件表示新闻推送的 SMTP 配置和账号邮箱均可用。",
                "<p>这是一封测试邮件。</p><p>收到此邮件表示新闻推送的 SMTP 配置和账号邮箱均可用。</p>",
                config=smtp_config,
            )
        except Exception as exc:
            raise BizError(f"测试邮件发送失败：{exc}", code=3094) from exc

    async def create_manual_delivery(self, user: User) -> NewsDelivery:
        recipient = self._require_email(user)
        state = await self.get_settings(user)
        missing = [
            label
            for key, label in (
                ("smtp", "SMTP 发件服务"),
                ("chat_model", "默认对话模型"),
                ("web_search", "联网搜索模型"),
            )
            if not state["readiness"][key]
        ]
        if missing:
            raise BizError(f"请先配置：{'、'.join(missing)}", code=3095)
        subscription = await self.repo.get_subscription(user.id)
        delivery = NewsDelivery(
            user_id=user.id,
            subscription_id=subscription.id if subscription else None,
            trigger=TRIGGER_MANUAL,
            status=STATUS_QUEUED,
            recipient_email=recipient,
        )
        created = await self.repo.create_delivery(delivery)
        if created is None:
            raise BizError("无法创建发送任务，请稍后重试", code=3091)
        return created

    async def create_scheduled_deliveries(self) -> list[NewsDelivery]:
        created: list[NewsDelivery] = []
        today = datetime.now(SHANGHAI_TZ).date().isoformat()
        users = UserRepository(self.session)
        for subscription in await self.repo.list_enabled():
            user = await users.get_by_id(subscription.user_id)
            if user is None or not user.email:
                logger.warning("跳过无邮箱的新闻订阅: user=%s", subscription.user_id)
                continue
            if not self._smtp_configured(subscription):
                logger.warning("跳过未配置 SMTP 的新闻订阅: user=%s", subscription.user_id)
                continue
            delivery = NewsDelivery(
                user_id=user.id,
                subscription_id=subscription.id,
                trigger=TRIGGER_SCHEDULED,
                status=STATUS_QUEUED,
                dedupe_key=f"news:{user.id}:{today}",
                recipient_email=user.email,
            )
            saved = await self.repo.create_delivery(delivery)
            if saved is not None:
                created.append(saved)
        return created

    async def run_delivery(self, delivery_id: uuid.UUID) -> None:
        delivery = await self.repo.get_delivery_by_id(delivery_id)
        if delivery is None:
            raise RuntimeError("新闻发送记录不存在")

        tracer = get_tracer()
        async with tracer.trace(
            user_id=delivery.user_id,
            task_type="news",
            task_id=delivery.id,
            task_name="每日新闻推送",
            attributes={"trigger": delivery.trigger},
        ):
            async with tracer.span("每日新闻推送", span_type="other"):
                delivery.status = STATUS_GENERATING
                delivery.started_at = datetime.now(timezone.utc)
                delivery.error_message = None
                await self.repo.save_delivery(delivery)

                user = await UserRepository(self.session).get_by_id(delivery.user_id)
                if user is None:
                    raise RuntimeError("账号不存在")
                if not user.email:
                    raise RuntimeError("账号邮箱未设置")
                subscription = await self.repo.get_subscription(user.id)
                topics = subscription.topics if subscription else []
                digest = await self._generate_digest(user.id, topics)
                subject, text_body, html_body = self._render_email(digest)
                delivery.recipient_email = user.email
                delivery.subject = subject
                smtp_config = self._smtp_config(subscription)
                await send_email(user.email, subject, text_body, html_body, config=smtp_config)
                delivery.status = STATUS_SENT
                delivery.finished_at = datetime.now(timezone.utc)
                await self.repo.save_delivery(delivery)

    async def record_delivery_failure(
        self, delivery_id: uuid.UUID, exc: Exception, *, final: bool
    ) -> None:
        """Record retry progress without presenting a transient failure as final."""
        delivery = await self.repo.get_delivery_by_id(delivery_id)
        if delivery is None:
            return
        delivery.status = STATUS_FAILED if final else STATUS_QUEUED
        delivery.error_message = str(exc)[:2000]
        delivery.finished_at = datetime.now(timezone.utc) if final else None
        await self.repo.save_delivery(delivery)

    async def _generate_digest(self, user_id: uuid.UUID, topics: list[str]) -> dict:
        search_config = await get_websearch_config(self.session, user_id)
        if search_config is None:
            raise RuntimeError("未配置联网搜索模型，请先在模型配置中添加")
        provider, api_key = search_config
        today = datetime.now(SHANGHAI_TZ).date()
        queries = [
            f"{today.isoformat()} 最近24小时 中国 国际 财经 科技 重大新闻",
            f"{today.isoformat()} 最近24小时 国内外重要新闻",
        ]
        queries.extend(f"{today.isoformat()} 最近24小时 {topic} 最新新闻" for topic in topics)

        results = await asyncio.gather(
            *[
                web_search_structured(
                    provider, api_key, query, top_k=8, topic="news", days=1
                )
                for query in queries
            ]
        )
        sources: list[dict] = []
        seen: set[str] = set()
        for group in results:
            for item in group:
                url = (item.get("url") or "").strip()
                title = (item.get("title") or "").strip()
                snippet = (item.get("snippet") or "").strip()
                if not url or not title or not snippet or url in seen:
                    continue
                seen.add(url)
                sources.append({"title": title, "url": url, "snippet": snippet[:1200]})
        sources = sources[:30]
        if not sources:
            raise RuntimeError("最近 24 小时没有检索到可用新闻来源")

        model, _ = await build_default_chat_model(
            self.session, user_id, temperature=0.2, streaming=False
        )
        source_text = "\n\n".join(
            f"[{i}] 标题：{item['title']}\n摘要：{item['snippet']}\n链接：{item['url']}"
            for i, item in enumerate(sources, 1)
        )
        topic_text = "、".join(topics) if topics else "无额外兴趣主题"
        response = await model.ainvoke(
            [
                SystemMessage(
                    content=(
                        "你是严谨的中文新闻编辑。只能使用用户提供的编号来源，不得补充、猜测或编造事实。"
                        "合并重复事件，优先重大综合要闻，并兼顾用户兴趣。有效来源不足时少选，不要凑数。"
                        "仅输出合法 JSON。"
                    )
                ),
                HumanMessage(
                    content=(
                        f"今天是 {today.isoformat()}，用户兴趣：{topic_text}。有效来源充分时精选 8 至 10 条，"
                        "来源不足时可少于 8 条，但至少 1 条。输出结构："
                        '{"title":"今日新闻晨报","intro":"一句话导语","items":['
                        '{"source_index":1,"headline":"标题","summary":"2至3句中文摘要",'
                        '"category":"要闻或兴趣主题"}]}。source_index 必须指向对应来源。\n\n'
                        f"{source_text}"
                    )
                ),
            ]
        )
        push_llm_usage(response, model)
        raw = response.content if isinstance(response.content, str) else str(response.content)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        payload = json.loads(raw)
        items: list[dict] = []
        for item in payload.get("items") or []:
            try:
                source_index = int(item.get("source_index"))
            except (TypeError, ValueError):
                continue
            if not 1 <= source_index <= len(sources):
                continue
            source = sources[source_index - 1]
            headline = str(item.get("headline") or source["title"]).strip()
            summary = str(item.get("summary") or "").strip()
            if not headline or not summary:
                continue
            items.append(
                {
                    "headline": headline[:180],
                    "summary": summary[:800],
                    "category": str(item.get("category") or "要闻")[:30],
                    "url": source["url"],
                    "source_title": source["title"],
                }
            )
            if len(items) == 10:
                break
        if not items:
            raise RuntimeError("AI 未能从检索来源生成有效的新闻摘要")
        return {
            "title": str(payload.get("title") or "今日新闻晨报")[:100],
            "intro": str(payload.get("intro") or "").strip()[:300],
            "date": today.isoformat(),
            "items": items,
        }

    @staticmethod
    def _render_email(digest: dict) -> tuple[str, str, str]:
        subject = f"回声新闻晨报 | {digest['date']}"
        text_lines = [digest["title"], digest["intro"], ""]
        html_items: list[str] = []
        for index, item in enumerate(digest["items"], 1):
            text_lines.extend(
                [
                    f"{index}. {item['headline']} [{item['category']}]",
                    item["summary"],
                    f"来源：{item['source_title']} {item['url']}",
                    "",
                ]
            )
            html_items.append(
                "<article style='margin:0 0 24px'>"
                f"<div style='color:#667085;font-size:12px'>{html.escape(item['category'])}</div>"
                f"<h2 style='font-size:18px;margin:4px 0 8px'>{html.escape(item['headline'])}</h2>"
                f"<p style='line-height:1.7;margin:0 0 8px'>{html.escape(item['summary'])}</p>"
                f"<a href='{html.escape(item['url'], quote=True)}'>阅读原文 · {html.escape(item['source_title'])}</a>"
                "</article>"
            )
        html_body = (
            "<main style='max-width:680px;margin:auto;font-family:Arial,sans-serif;color:#101828'>"
            f"<h1 style='font-size:26px'>{html.escape(digest['title'])}</h1>"
            f"<p style='color:#475467;line-height:1.7'>{html.escape(digest['intro'])}</p>"
            + "".join(html_items)
            + "<p style='color:#98a2b3;font-size:12px'>此邮件由回声 Echo 根据联网来源自动整理。</p></main>"
        )
        return subject, "\n".join(text_lines), html_body

    @staticmethod
    def _require_email(user: User) -> str:
        if not user.email:
            raise BizError("请先在个人资料中设置邮箱", code=3092)
        return user.email

    @staticmethod
    def _smtp_configured(subscription) -> bool:
        return bool(
            subscription
            and subscription.smtp_provider in SMTP_PROVIDERS
            and subscription.smtp_username
            and subscription.smtp_password_encrypted
        )

    @classmethod
    def _smtp_config(cls, subscription) -> SmtpConfig:
        if not cls._smtp_configured(subscription):
            raise BizError("请先配置 SMTP 发件服务", code=3096)
        host, port, security = SMTP_PROVIDERS[subscription.smtp_provider]
        return SmtpConfig(
            host=host,
            port=port,
            username=subscription.smtp_username,
            password=decrypt_secret(subscription.smtp_password_encrypted),
            from_email=subscription.smtp_username,
            from_name=subscription.smtp_from_name or "回声 Echo",
            security=security,
        )

    @staticmethod
    def delivery_dict(delivery: NewsDelivery) -> dict:
        return {
            "id": str(delivery.id),
            "trigger": delivery.trigger,
            "status": delivery.status,
            "recipient_email": delivery.recipient_email,
            "subject": delivery.subject,
            "error_message": delivery.error_message,
            "started_at": delivery.started_at.isoformat() if delivery.started_at else None,
            "finished_at": delivery.finished_at.isoformat() if delivery.finished_at else None,
            "created_at": delivery.created_at.isoformat() if delivery.created_at else None,
        }
