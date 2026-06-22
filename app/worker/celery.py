from celery import Celery

from app.core.config import REDIS_URL

celery_app = Celery("drone_tasks", broker=REDIS_URL, backend=REDIS_URL)
