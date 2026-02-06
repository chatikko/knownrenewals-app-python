from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class CommonResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    message: str | None = None
    status_code: int


class ListResponse(BaseModel, Generic[T]):
    success: bool = True
    items: list[T]
    total: int
    status_code: int
