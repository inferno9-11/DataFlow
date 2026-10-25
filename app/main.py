import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_v1_router
from app.api.v1.routes.health import router as health_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db.base import Base
from app.db.session import async_engine
from app.middleware import RequestIdMiddleware, TimingAndMetricsMiddleware, register_error_handlers

settings = get_settings()
setup_logging(level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)
logger = get_logger("dataflow.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan lifecycle manager.
    Initializes infrastructure connections and performs graceful teardown.
    """
    logger.info(
        f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT.upper()} mode]"
    )

    # In local development or test SQLite environments, ensure tables are created
    if "sqlite" in settings.DATABASE_URL.lower():
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("SQLite database tables verified/created for local development/testing.")

    yield

    logger.info("Initiating graceful shutdown: disposing database connection pool...")
    await async_engine.dispose()
    logger.info("DataFlow application shutdown complete.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Production-Grade Backend API and Asynchronous Data Processing Platform",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# 1. Register Error Handlers
register_error_handlers(app)

# 2. Register Middleware (executed in reverse order: RequestId first, then Timing, then CORS)
app.add_middleware(TimingAndMetricsMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time"],
)

# 3. Mount Routers
app.include_router(health_router)
app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

# 4. Interactive Live Demo UI
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse, tags=["Dashboard"], include_in_schema=False)
async def serve_dashboard():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse(
        "<h1>DataFlow API is running. Visit <a href='/docs'>/docs</a> for Swagger documentation.</h1>"
    )
