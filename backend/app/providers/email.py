from abc import ABC, abstractmethod
from dataclasses import dataclass

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


def get_email_provider() -> EmailProvider:
    if settings.email_provider != "stub":
        raise RuntimeError(f"Email provider '{settings.email_provider}' is not installed")
    return StubEmailProvider()
