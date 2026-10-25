from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "dataflow_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 min hard timeout
    task_soft_time_limit=540,  # 9 min soft timeout
    worker_prefetch_multiplier=1,  # Fair distribution among workers
    task_acks_late=True,  # Guarantees at-least-once task delivery
    broker_connection_retry_on_startup=False,
    broker_transport_options={
        "socket_timeout": 1.0,
        "socket_connect_timeout": 1.0,
        "max_connections": 10,
    },
)
