"""SMTP email transport for Echo notifications."""
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr

import aiosmtplib

from app.config import settings


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    from_email: str
    from_name: str
    security: str


def _global_config() -> SmtpConfig:
    return SmtpConfig(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        from_email=settings.smtp_from_email,
        from_name=settings.smtp_from_name,
        security=settings.smtp_security,
    )


def smtp_ready(config: SmtpConfig | None = None) -> bool:
    selected = config or _global_config()
    return bool(selected.host and selected.from_email)


async def send_email(
    recipient: str,
    subject: str,
    text_content: str,
    html_content: str,
    *,
    config: SmtpConfig | None = None,
) -> None:
    selected = config or _global_config()
    if not smtp_ready(selected):
        raise RuntimeError("SMTP 尚未配置，请先设置发件服务器和发件地址")
    security = selected.security.lower()
    if security not in {"starttls", "ssl", "none"}:
        raise RuntimeError("SMTP_SECURITY 必须是 starttls、ssl 或 none")

    message = EmailMessage()
    message["From"] = formataddr((selected.from_name, selected.from_email))
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(text_content)
    message.add_alternative(html_content, subtype="html")

    smtp = aiosmtplib.SMTP(
        hostname=selected.host,
        port=selected.port,
        use_tls=security == "ssl",
        start_tls=False,
        timeout=30,
    )
    await smtp.connect()
    try:
        if security == "starttls":
            await smtp.starttls()
        if selected.username:
            await smtp.login(selected.username, selected.password)
        await smtp.send_message(message)
    finally:
        await smtp.quit()
