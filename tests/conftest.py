import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB_FILE = os.path.join(os.path.dirname(__file__), "test_dataflow.db")
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_FILE}"
TEST_SYNC_DATABASE_URL = f"sqlite:///{TEST_DB_FILE}"

# Force testing configuration
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["DATABASE_SYNC_URL"] = TEST_SYNC_DATABASE_URL
os.environ["SECRET_KEY"] = "test-secret-key-for-dataflow-at-least-32-chars-long"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["LOG_LEVEL"] = "WARNING"

from app.core.config import get_settings

get_settings.cache_clear()

import app.db.session as app_session
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Align app global engine and session factory with test database
app_session.async_engine = test_engine
app_session.async_session_factory = TestingSessionLocal


@pytest.fixture(scope="session", autouse=True)
def clean_test_db_file():
    """Ensure clean test database file before and after test session."""
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except OSError:
            pass
    yield
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except OSError:
            pass


@pytest.fixture(autouse=True)
async def setup_database():
    """Create all schema tables before each test and drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db():
    async with TestingSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
async def db_session() -> AsyncSession:
    async with TestingSessionLocal() as session:
        yield session


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        email="testuser@dataflow.dev",
        hashed_password=hash_password("Password123!Secure"),
        full_name="Test User",
        role="user",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def auth_headers(test_user: User) -> dict:
    token = create_access_token(subject=str(test_user.id), role=test_user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def second_user(db_session: AsyncSession) -> User:
    user = User(
        email="seconduser@dataflow.dev",
        hashed_password=hash_password("Password123!Secure"),
        full_name="Second User",
        role="user",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def second_user_headers(second_user: User) -> dict:
    token = create_access_token(subject=str(second_user.id), role=second_user.role)
    return {"Authorization": f"Bearer {token}"}
