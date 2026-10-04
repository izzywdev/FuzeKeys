"""Shared bounded offset pagination contract for API collections."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PageInfo(BaseModel):
    offset: int
    limit: int
    total: int
    next_offset: int | None


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: PageInfo


def paginate(items: list[T], offset: int, limit: int) -> Page[T]:
    """Paginate a bounded in-memory catalog; database queries must limit in SQL."""
    total = len(items)
    return Page(items=items[offset : offset + limit], page=PageInfo(
        offset=offset, limit=limit, total=total,
        next_offset=offset + limit if offset + limit < total else None,
    ))
