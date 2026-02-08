import aiosmtplib
import asyncio
from email.message import EmailMessage
import random
import time
from urllib.parse import quote

from app.core.config import get_settings

settings = get_settings()


class EmailService:
    def __init__(self) -> None:
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._user = settings.smtp_user
        self._password = settings.smtp_password
        self._mail_from = settings.mail_from
        self._frontend_base_url = settings.frontend_base_url.rstrip("/")
        # Port 465 expects implicit TLS, while 587/2525 usually upgrade with STARTTLS.
        self._use_tls = self._port == 465
        self._start_tls = self._port in (587, 2525)
        self._timeout_seconds = settings.smtp_timeout_seconds
        self._max_retries = settings.smtp_max_retries
        self._base_backoff_seconds = settings.smtp_base_backoff_seconds
        self._max_idle_seconds = settings.smtp_max_idle_seconds
        self._smtp_client: aiosmtplib.SMTP | None = None
        self._last_used_monotonic = 0.0
        self._lock = asyncio.Lock()

    def _new_client(self) -> aiosmtplib.SMTP:
        return aiosmtplib.SMTP(
            hostname=self._host,
            port=self._port,
            use_tls=self._use_tls,
            start_tls=self._start_tls,
            timeout=self._timeout_seconds,
        )

    async def _disconnect_locked(self) -> None:
        if not self._smtp_client:
            return
        try:
            if self._smtp_client.is_connected:
                await self._smtp_client.quit()
        except Exception:
            try:
                await self._smtp_client.close()
            except Exception:
                pass
        finally:
            self._smtp_client = None
            self._last_used_monotonic = 0.0

    async def _connect_locked(self) -> None:
        await self._disconnect_locked()
        client = self._new_client()
        await client.connect()
        if self._user and self._password:
            await client.login(self._user, self._password)
        self._smtp_client = client
        self._last_used_monotonic = time.monotonic()

    async def _get_client_locked(self) -> aiosmtplib.SMTP:
        now = time.monotonic()
        if (
            self._smtp_client
            and self._smtp_client.is_connected
            and now - self._last_used_monotonic <= self._max_idle_seconds
        ):
            return self._smtp_client
        await self._connect_locked()
        return self._smtp_client  # type: ignore[return-value]

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        name = exc.__class__.__name__
        retryable_names = {
            "SMTPConnectError",
            "SMTPServerDisconnected",
            "SMTPTimeoutError",
            "SMTPReadTimeoutError",
            "SMTPConnectTimeoutError",
            "SMTPResponseException",
        }
        if name in retryable_names:
            code = getattr(exc, "code", None)
            smtp_code = getattr(exc, "smtp_code", None)
            candidate = code if code is not None else smtp_code
            if candidate is None:
                return True
            return 400 <= int(candidate) < 500
        return isinstance(exc, (TimeoutError, OSError, ConnectionError))

    async def close(self) -> None:
        async with self._lock:
            await self._disconnect_locked()

    async def check_connection(self) -> None:
        async with self._lock:
            await self._connect_locked()

    async def send_email(self, to_email: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._mail_from
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)
        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                async with self._lock:
                    client = await self._get_client_locked()
                    await client.send_message(message)
                    self._last_used_monotonic = time.monotonic()
                    return
            except Exception as exc:
                last_exc = exc
                async with self._lock:
                    await self._disconnect_locked()
                if attempt >= self._max_retries or not self._is_retryable(exc):
                    raise
                delay = self._base_backoff_seconds * (2**attempt) + random.uniform(0, 0.25)
                await asyncio.sleep(delay)

        if last_exc:
            raise last_exc

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
