from typing import Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic repository providing shared database session access."""

    def __init__(self, model: type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session
