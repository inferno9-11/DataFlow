import uuid

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConflictError, NotFoundError
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import TokenResponse, UserLoginRequest, UserRegisterRequest, UserResponse

settings = get_settings()


class AuthService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def register_user(self, payload: UserRegisterRequest) -> UserResponse:
        # Check if user already exists
        existing = await self.user_repo.get_by_email(payload.email)
        if existing:
            raise ConflictError(f"A user with email '{payload.email}' already exists.")

        hashed_pw = hash_password(payload.password)
        new_user = User(
            email=payload.email.lower().strip(),
            hashed_password=hashed_pw,
            full_name=payload.full_name.strip(),
            role=payload.role,
            is_active=True,
        )
        created_user = await self.user_repo.create(new_user)
        return UserResponse.model_validate(created_user)

    async def login_user(self, payload: UserLoginRequest) -> TokenResponse:
        user = await self.user_repo.get_by_email(payload.email)
        if not user:
            raise AuthenticationError("Invalid email or password.")

        if not user.is_active:
            raise AuthenticationError("This user account has been deactivated.")

        if not verify_password(payload.password, user.hashed_password):
            raise AuthenticationError("Invalid email or password.")

        token = create_access_token(
            subject=str(user.id),
            role=user.role,
        )

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=user.id,
            role=user.role,
            full_name=user.full_name,
        )

    async def get_user_profile(self, user_id: uuid.UUID) -> UserResponse:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)
        return UserResponse.model_validate(user)
