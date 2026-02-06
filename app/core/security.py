from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        # bcrypt rejects passwords longer than 72 bytes.
        return False


def _create_token(
    data: dict[str, Any],
    secret: str,
    expires_delta: timedelta,
    algorithm: str = "HS256",
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, secret, algorithm=algorithm)


def create_access_token(subject: str, secret: str, expires_minutes: int) -> str:
    return _create_token({"sub": subject, "type": "access"}, secret, timedelta(minutes=expires_minutes))


def create_refresh_token(subject: str, secret: str, expires_minutes: int) -> str:
    return _create_token({"sub": subject, "type": "refresh"}, secret, timedelta(minutes=expires_minutes))


def decode_token(token: str, secret: str, token_type: Literal["access", "refresh"]) -> dict[str, Any]:
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    if payload.get("type") != token_type:
        raise JWTError("Invalid token type")
    return payload
