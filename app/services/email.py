import aiosmtplib
from email.message import EmailMessage

from app.core.config import get_settings

settings = get_settings()


class EmailService:
    def __init__(self) -> None:
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._user = settings.smtp_user
        self._password = settings.smtp_password
        self._mail_from = settings.mail_from
        self._start_tls = self._port in (587, 2525)

    async def send_email(self, to_email: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._mail_from
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        await aiosmtplib.send(
            message,
            hostname=self._host,
            port=self._port,
            username=self._user,
            password=self._password,
            start_tls=self._start_tls,
        )

    async def send_verification_email(self, to_email: str, token: str) -> None:
        subject = "[knowrenewals] Verify your email"
        body = (
            "Welcome to knowrenewals.\n\n"
            "Use the token below to verify your email address:\n\n"
            f"{token}\n\n"
            "If you did not sign up, you can ignore this email."
        )
        await self.send_email(to_email, subject, body)


email_service = EmailService()
