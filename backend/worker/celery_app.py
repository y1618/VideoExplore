from celery import Celery

from app.config import settings

celery_app = Celery(
    "videoexplore",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["worker.tasks"],
)

celery_app.conf.update(
    task_default_queue="cpu",
    task_routes={
        "worker.tasks.tag_video": {"queue": "gpu"},
        "worker.tasks.caption_video": {"queue": "gpu"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=1800,
    task_soft_time_limit=1500,
)
