import asyncio
import smtplib
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage

from app.config import settings


@dataclass
class EmailMessage:
    to: str
    subject: str
    body: str


@dataclass
class SendResult:
    accepted: bool
    provider: str
    external_id: str | None = None


@dataclass
class EmailReply:
    sender: str
    subject: str
    body: str


class EmailProvider(ABC):
    @abstractmethod
    async def send(self, message: EmailMessage) -> SendResult: ...

    @abstractmethod
    async def fetch_replies(self) -> list[EmailReply]: ...


class StubEmailProvider(EmailProvider):
    async def send(self, message: EmailMessage) -> SendResult:
        return SendResult(accepted=False, provider="stub")

    async def fetch_replies(self) -> list[EmailReply]:
        return []


def smtp_missing_settings() -> list[str]:
    required = {
        "SMTP_HOST": settings.smtp_host,
        "SMTP_USERNAME": settings.smtp_username,
        "SMTP_PASSWORD": settings.smtp_password,
        "EMAIL_FROM_ADDRESS": settings.email_from_address,
        "ADMIN_NOTIFICATION_EMAIL": settings.admin_notification_email,
    }
    return [name for name, value in required.items() if not value]


def email_delivery_ready() -> bool:
    return settings.email_provider == "smtp" and not smtp_missing_settings()


class SMTPEmailProvider(EmailProvider):
    async def send(self, message: EmailMessage) -> SendResult:
        await asyncio.to_thread(self._send_sync, message)
        return SendResult(accepted=True, provider="smtp")

    def _send_sync(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = settings.email_from_address
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.body)
        if settings.smtp_security == "ssl":
            client = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds, context=ssl.create_default_context())
        else:
            client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds)
        with client as connection:
            if settings.smtp_security == "starttls":
                connection.starttls(context=ssl.create_default_context())
            connection.login(settings.smtp_username, settings.smtp_password)
            connection.send_message(mime)

    async def fetch_replies(self) -> list[EmailReply]:
        return []


def get_email_provider() -> EmailProvider:
    if settings.email_provider in {"stub", "disabled"}:
        return StubEmailProvider()
    if settings.email_provider == "smtp":
        missing = smtp_missing_settings()
        if missing:
            raise RuntimeError(f"SMTP email configuration is incomplete: {', '.join(missing)}")
        return SMTPEmailProvider()
    raise RuntimeError(f"Email provider '{settings.email_provider}' is not installed")
