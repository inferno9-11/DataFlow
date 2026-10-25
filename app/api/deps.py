import uuid
from collections.abc import Callable

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError, AuthorizationError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.job_repository import JobRepository
from app.repositories.record_repository import RecordRepository
from app.repositories.user_repository import UserRepository
from app.services.analytics_service import AnalyticsService
from app.services.auth_service import AuthService
from app.services.job_service import JobService
from app.services.record_service import RecordService


async def get_token_from_header(authorization: str | None = Header(None)) -> str:
    """Extracts Bearer token from HTTP Authorization header."""
    if not authorization:
        raise AuthenticationError("Authorization header missing.")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthenticationError("Invalid Authorization header format. Expected 'Bearer <token>'.")

    return parts[1]


# Repositories Dependencies
def get_user_repository(session: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(session)


def get_record_repository(session: AsyncSession = Depends(get_db)) -> RecordRepository:
    return RecordRepository(session)


def get_job_repository(session: AsyncSession = Depends(get_db)) -> JobRepository:
    return JobRepository(session)


# Services Dependencies
def get_auth_service(user_repo: UserRepository = Depends(get_user_repository)) -> AuthService:
    return AuthService(user_repo)


def get_record_service(
    record_repo: RecordRepository = Depends(get_record_repository),
) -> RecordService:
    return RecordService(record_repo)


def get_job_service(job_repo: JobRepository = Depends(get_job_repository)) -> JobService:
    return JobService(job_repo)


def get_analytics_service(
    record_repo: RecordRepository = Depends(get_record_repository),
) -> AnalyticsService:
    return AnalyticsService(record_repo)


# User Authentication Dependency
async def get_current_user(
    token: str = Depends(get_token_from_header),
    user_repo: UserRepository = Depends(get_user_repository),
) -> User:
    """
    Decodes token, validates claims, and retrieves the active user entity.
    """
    payload = decode_access_token(token)
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise AuthenticationError("Token payload missing subject claim.")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise AuthenticationError("Invalid user ID in token subject.") from None

    user = await user_repo.get_by_id(user_id)
    if not user:
        raise AuthenticationError("User not found or revoked.")

    if not user.is_active:
        raise AuthenticationError("User account has been deactivated.")

    return user


def require_role(allowed_roles: list[str]) -> Callable[[User], User]:
    """Factory creating an authorization dependency enforcing role membership."""

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise AuthorizationError(
                f"Action requires one of the following roles: {', '.join(allowed_roles)}."
            )
        return current_user

    return role_checker
