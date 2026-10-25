from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error identifier")
    message: str = Field(..., description="Human-readable description of the error")
    request_id: str = Field(..., description="Correlation ID for request tracing")
    details: Any | None = Field(
        default=None, description="Detailed field-level validation errors or context"
    )


class ErrorResponse(BaseModel):
    error: ErrorDetail


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, description="Page number starting at 1")
    page_size: int = Field(default=50, ge=1, le=1000, description="Items per page (max 1000)")


class PaginatedResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(from_attributes=True)

    items: list[T]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool

    @classmethod
    def create(
        cls, items: list[T], total_count: int, page: int, page_size: int
    ) -> "PaginatedResponse[T]":
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        return cls(
            items=items,
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )


class MessageResponse(BaseModel):
    message: str
    request_id: str | None = None
