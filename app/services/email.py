import asyncio
import random
from urllib.parse import quote

import resend

from app.core.config import get_settings

settings = get_settings()


class EmailService:
    def __init__(self) -> None:
        self._api_key = settings.resend_api_key
        self._mail_from = settings.mail_from
        self._frontend_base_url = settings.frontend_base_url.rstrip("/")
        self._max_retries = settings.resend_max_retries
        self._base_backoff_seconds = settings.resend_base_backoff_seconds
        resend.api_key = self._api_key

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        if status_code is not None:
            if status_code == 429:
                return True
            return 500 <= int(status_code) < 600
        name = exc.__class__.__name__
        return name in {"Timeout", "ConnectTimeout", "ReadTimeout", "ConnectionError"} or isinstance(
            exc, (TimeoutError, OSError, ConnectionError)
        )

    def _assert_resend_config(self) -> None:
        if not self._api_key:
            raise RuntimeError("RESEND_API_KEY is not configured")
        if not self._mail_from:
            raise RuntimeError("MAIL_FROM is not configured")

    async def close(self) -> None:
        return

    async def check_connection(self) -> None:
        self._assert_resend_config()
        await asyncio.to_thread(resend.Domains.list)

    async def _send_payload(self, payload: resend.Emails.SendParams) -> None:
        self._assert_resend_config()
        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                await asyncio.to_thread(resend.Emails.send, payload)
                return
            except Exception as exc:
                last_exc = exc
                if attempt >= self._max_retries or not self._is_retryable(exc):
                    raise
                delay = self._base_backoff_seconds * (2**attempt) + random.uniform(0, 0.25)
                await asyncio.sleep(delay)

        if last_exc:
            raise last_exc

    async def send_email(self, to_email: str, subject: str, body: str) -> None:
        payload: resend.Emails.SendParams = {
            "from": self._mail_from,
            "to": [to_email],
            "subject": subject,
            "text": body,
        }
        await self._send_payload(payload)

    async def send_email_with_attachment(
        self,
        to_email: str,
        subject: str,
        body: str,
        filename: str,
        content_bytes: bytes,
        mime_type: str,
    ) -> None:
        payload: resend.Emails.SendParams = {
            "from": self._mail_from,
            "to": [to_email],
            "subject": subject,
            "text": body,
            "attachments": [
                {
                    "filename": filename,
                    "content_type": mime_type,
                    "content": list(content_bytes),
                }
            ],
        }
        await self._send_payload(payload)

    async def send_verification_email(self, to_email: str, token: str) -> None:
        encoded_token = quote(token, safe="")
        encoded_email = quote(to_email, safe="")
        verify_url = f"{self._frontend_base_url}/verify-email?token={encoded_token}&email={encoded_email}"
        subject = "[knowrenewals] Verify your email"
        body = (
            "Welcome to knowrenewals.\n\n"
            "Verify your email address by opening this link:\n\n"
            f"{verify_url}\n\n"
            "If you did not sign up, you can ignore this email."
        )
        await self.send_email(to_email, subject, body)


email_service = EmailService()
