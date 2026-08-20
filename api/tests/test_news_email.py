import json
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.exceptions import BizError
from app.core.news import mailer
from app.core.news.mailer import SmtpConfig
from app.core.agent import web_search
from app.models.user_model import User
from app.models.news_delivery_model import (
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_SENT,
    NewsDelivery,
)
from app.models.news_subscription_model import NewsSubscription
from app.schemas.news_schema import NewsSmtpUpdate, NewsSubscriptionUpdate
from app.services.auth_service import AuthService
from app.services.news_service import NewsService


class NewsSchemaTests(unittest.TestCase):
    def test_topics_are_trimmed_and_deduplicated(self):
        body = NewsSubscriptionUpdate(topics=[" AI ", "ai", "宏观经济", ""])
        self.assertEqual(body.topics, ["AI", "宏观经济"])

    def test_rejects_more_than_six_topics(self):
        with self.assertRaises(ValueError):
            NewsSubscriptionUpdate(topics=[str(i) for i in range(7)])


class AuthEmailTests(unittest.IsolatedAsyncioTestCase):
    async def test_email_is_normalized_and_unique(self):
        user = User(id=uuid.uuid4(), username="owner", password_hash="hash")
        repo = AsyncMock()
        repo.get_by_login.return_value = None
        repo.update_profile.return_value = user
        service = AuthService.__new__(AuthService)
        service.repo = repo

        await service.update_profile(
            user,
            nickname=None,
            email="  Name@Example.COM ",
            fields_set={"email"},
        )
        self.assertEqual(repo.update_profile.await_args.kwargs["email"], "name@example.com")
        self.assertEqual(repo.update_profile.await_args.kwargs["username"], "name@example.com")

    async def test_duplicate_email_is_rejected(self):
        user = User(id=uuid.uuid4(), username="owner", password_hash="hash")
        other = User(id=uuid.uuid4(), username="other", password_hash="hash")
        repo = AsyncMock()
        repo.get_by_login.return_value = other
        service = AuthService.__new__(AuthService)
        service.repo = repo
        with self.assertRaisesRegex(BizError, "已被其他账号使用"):
            await service.update_profile(
                user,
                nickname=None,
                email="name@example.com",
                fields_set={"email"},
            )

    async def test_registration_uses_email_as_account_and_recipient(self):
        user = User(
            id=uuid.uuid4(),
            username="name@example.com",
            email="name@example.com",
            password_hash="hash",
        )
        repo = AsyncMock()
        repo.get_by_login.return_value = None
        repo.create.return_value = user
        service = AuthService.__new__(AuthService)
        service.repo = repo

        created = await service.register(" Name@Example.COM ", "password")

        self.assertEqual(created.email, "name@example.com")
        repo.create.assert_awaited_once()
        self.assertEqual(repo.create.await_args.args[0], "name@example.com")
        self.assertEqual(repo.create.await_args.kwargs["email"], "name@example.com")


class NewsGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_smtp_password_is_encrypted_before_saving(self):
        service = NewsService(AsyncMock())
        user = User(
            id=uuid.uuid4(), username="owner", password_hash="hash", email="reader@example.com"
        )
        service.repo = AsyncMock()
        service.repo.get_subscription.return_value = None
        service.get_settings = AsyncMock(return_value={"readiness": {"smtp": True}})
        body = NewsSmtpUpdate(
            provider="qq",
            sender_email=" Sender@QQ.COM ",
            password="authorization-code",
            from_name="回声 Echo",
        )

        with patch("app.services.news_service.encrypt_secret", return_value="ciphertext"):
            await service.update_smtp(user, body)

        saved = service.repo.save_smtp.await_args.kwargs
        self.assertEqual(saved["username"], "sender@qq.com")
        self.assertEqual(saved["password_encrypted"], "ciphertext")

    async def test_changing_smtp_account_requires_new_password(self):
        service = NewsService(AsyncMock())
        user = User(id=uuid.uuid4(), username="owner", password_hash="hash")
        service.repo = AsyncMock()
        service.repo.get_subscription.return_value = NewsSubscription(
            id=uuid.uuid4(),
            user_id=user.id,
            smtp_provider="qq",
            smtp_username="old@qq.com",
            smtp_password_encrypted="ciphertext",
        )
        body = NewsSmtpUpdate(
            provider="163", sender_email="new@163.com", from_name="回声 Echo"
        )

        with self.assertRaisesRegex(BizError, "授权码"):
            await service.update_smtp(user, body)

    async def test_email_is_required_before_enabling_or_sending(self):
        service = NewsService(AsyncMock())
        user = User(
            id=uuid.uuid4(), username="owner", password_hash="hash", email=None
        )

        with self.assertRaisesRegex(BizError, "设置邮箱"):
            await service.update_settings(
                user, NewsSubscriptionUpdate(enabled=True, topics=[])
            )
        with self.assertRaisesRegex(BizError, "设置邮箱"):
            await service.create_manual_delivery(user)

    async def test_scheduled_delivery_uses_daily_dedupe_key(self):
        service = NewsService(AsyncMock())
        user_id = uuid.uuid4()
        subscription = NewsSubscription(
            id=uuid.uuid4(), user_id=user_id, enabled=True,
            smtp_provider="qq", smtp_username="sender@qq.com",
            smtp_password_encrypted="encrypted",
        )
        user = User(
            id=user_id,
            username="owner",
            password_hash="hash",
            email="reader@example.com",
        )
        service.repo = AsyncMock()
        service.repo.list_enabled.return_value = [subscription]
        service.repo.create_delivery.side_effect = lambda delivery: delivery
        users = AsyncMock()
        users.get_by_id.return_value = user

        with patch("app.services.news_service.UserRepository", return_value=users):
            first = await service.create_scheduled_deliveries()

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].recipient_email, "reader@example.com")
        self.assertRegex(
            first[0].dedupe_key or "",
            rf"^news:{user_id}:\d{{4}}-\d{{2}}-\d{{2}}$",
        )

        service.repo.create_delivery.return_value = None
        service.repo.create_delivery.side_effect = None
        with patch("app.services.news_service.UserRepository", return_value=users):
            duplicate = await service.create_scheduled_deliveries()
        self.assertEqual(duplicate, [])

    async def test_delivery_reads_current_account_email_at_execution_time(self):
        service = NewsService(AsyncMock())
        user_id = uuid.uuid4()
        delivery = NewsDelivery(
            id=uuid.uuid4(),
            user_id=user_id,
            trigger="manual",
            status=STATUS_QUEUED,
            recipient_email="old@example.com",
        )
        current_user = User(
            id=user_id,
            username="owner",
            password_hash="hash",
            email="new@example.com",
        )
        digest = {
            "title": "晨报",
            "intro": "摘要",
            "date": "2026-08-20",
            "items": [],
        }
        service.repo = AsyncMock()
        service.repo.get_delivery_by_id.return_value = delivery
        service.repo.get_subscription.return_value = NewsSubscription(
            id=uuid.uuid4(), user_id=user_id, smtp_provider="qq",
            smtp_username="sender@qq.com", smtp_password_encrypted="encrypted",
        )
        users = AsyncMock()
        users.get_by_id.return_value = current_user

        with (
            patch("app.services.news_service.UserRepository", return_value=users),
            patch.object(service, "_generate_digest", new=AsyncMock(return_value=digest)),
            patch.object(
                service,
                "_smtp_config",
                return_value=SmtpConfig(
                    host="smtp.qq.com", port=465, username="sender@qq.com",
                    password="secret", from_email="sender@qq.com",
                    from_name="回声 Echo", security="ssl",
                ),
            ),
            patch("app.services.news_service.send_email", new=AsyncMock()) as send,
        ):
            await service.run_delivery(delivery.id)

        self.assertEqual(delivery.recipient_email, "new@example.com")
        self.assertEqual(delivery.status, STATUS_SENT)
        self.assertEqual(send.await_args.args[0], "new@example.com")
        self.assertEqual(send.await_args.kwargs["config"].username, "sender@qq.com")

    async def test_generated_items_must_reference_search_sources(self):
        service = NewsService(AsyncMock())
        response = {
            "title": "今日新闻晨报",
            "intro": "今日重点",
            "items": [
                {"source_index": 1, "headline": "有效新闻", "summary": "有效摘要", "category": "要闻"},
                {"source_index": 99, "headline": "无来源新闻", "summary": "不应保留", "category": "要闻"},
            ],
        }
        fake_model = AsyncMock()
        fake_model.ainvoke.return_value.content = json.dumps(response, ensure_ascii=False)
        sources = [{"title": "来源标题", "url": "https://example.com/news", "snippet": "新闻摘要"}]

        with (
            patch("app.services.news_service.get_websearch_config", new=AsyncMock(return_value=("tavily", "key"))),
            patch("app.services.news_service.web_search_structured", new=AsyncMock(return_value=sources)),
            patch("app.services.news_service.build_default_chat_model", new=AsyncMock(return_value=(fake_model, object()))),
        ):
            digest = await service._generate_digest(uuid.uuid4(), ["人工智能"])

        self.assertEqual(len(digest["items"]), 1)
        self.assertEqual(digest["items"][0]["url"], "https://example.com/news")

    def test_email_contains_plain_text_and_escaped_html(self):
        digest = {
            "title": "晨报",
            "intro": "摘要",
            "date": "2026-08-20",
            "items": [{
                "headline": "A < B",
                "summary": "内容",
                "category": "要闻",
                "url": "https://example.com/?a=1&b=2",
                "source_title": "示例来源",
            }],
        }
        subject, text_body, html_body = NewsService._render_email(digest)
        self.assertIn("2026-08-20", subject)
        self.assertIn("https://example.com", text_body)
        self.assertIn("A &lt; B", html_body)

    async def test_transient_delivery_failure_stays_queued_until_retries_end(self):
        service = NewsService(AsyncMock())
        delivery = NewsDelivery(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            trigger="manual",
            recipient_email="reader@example.com",
        )
        service.repo = AsyncMock()
        service.repo.get_delivery_by_id.return_value = delivery

        await service.record_delivery_failure(delivery.id, RuntimeError("temporary"), final=False)
        self.assertEqual(delivery.status, STATUS_QUEUED)
        self.assertIsNone(delivery.finished_at)

        await service.record_delivery_failure(delivery.id, RuntimeError("permanent"), final=True)
        self.assertEqual(delivery.status, STATUS_FAILED)
        self.assertIsNotNone(delivery.finished_at)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_starttls_sends_multipart_message(self):
        smtp = AsyncMock()
        with (
            patch.object(mailer.settings, "smtp_host", "smtp.example.com"),
            patch.object(mailer.settings, "smtp_port", 587),
            patch.object(mailer.settings, "smtp_username", "user"),
            patch.object(mailer.settings, "smtp_password", "secret"),
            patch.object(mailer.settings, "smtp_from_email", "echo@example.com"),
            patch.object(mailer.settings, "smtp_security", "starttls"),
            patch("app.core.news.mailer.aiosmtplib.SMTP", return_value=smtp) as smtp_class,
        ):
            await mailer.send_email("reader@example.com", "主题", "纯文本", "<p>HTML</p>")

        smtp_class.assert_called_once_with(
            hostname="smtp.example.com", port=587, use_tls=False, start_tls=False, timeout=30
        )
        smtp.starttls.assert_awaited_once()
        smtp.login.assert_awaited_once_with("user", "secret")
        sent = smtp.send_message.await_args.args[0]
        self.assertTrue(sent.is_multipart())

    async def test_tavily_news_parameters_are_forwarded(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"results": []}
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.post.return_value = response
        with patch("app.core.agent.web_search.httpx.AsyncClient", return_value=client):
            await web_search.web_search_structured(
                "tavily", "key", "最近新闻", top_k=5, topic="news", days=1
            )
        payload = client.post.await_args.kwargs["json"]
        self.assertEqual(payload["topic"], "news")
        self.assertEqual(payload["days"], 1)


if __name__ == "__main__":
    unittest.main()
