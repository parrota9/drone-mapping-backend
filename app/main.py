from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.storage as storage
from app.api.v1 import maps


@asynccontextmanager
async def lifespan(_app: FastAPI):
    storage.ensure_bucket()
    yield


app = FastAPI(title="Drone Photogrammetry Pipeline API", lifespan=lifespan)

app.include_router(maps.router, prefix="/api/v1")
