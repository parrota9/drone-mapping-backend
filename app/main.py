import os
import uuid
from contextlib import asynccontextmanager

from celery.result import AsyncResult
from fastapi import FastAPI, File, HTTPException, UploadFile

import storage
from tasks import celery_app, process_drone_mission


@asynccontextmanager
async def lifespan(_app: FastAPI):
    storage.ensure_bucket()
    yield


app = FastAPI(title="Drone Photogrammetry Pipeline API", lifespan=lifespan)


@app.post("/api/v1/maps/process")
async def upload_and_stitch_map(file: UploadFile = File(...)):
    if not file.filename.endswith(".zip"):
        raise HTTPException(
            status_code=400, detail="Only compressed .zip folders are supported."
        )

    task_id = str(uuid.uuid4())
    mission_id = os.path.splitext(file.filename)[0]
    upload_key = f"uploads/{task_id}/{file.filename}"

    storage.upload_fileobj(file.file, upload_key)

    async_task = process_drone_mission.apply_async(
        args=[upload_key, mission_id], task_id=task_id
    )

    return {
        "message": "Drone mission dataset successfully queued for processing.",
        "mission_id": mission_id,
        "task_id": async_task.id,
        "status": "Processing asynchronously in background",
    }


@app.get("/api/v1/maps/status/{task_id}")
async def get_processing_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    state = task_result.state

    response = {"task_id": task_id, "pipeline_state": state, "outputs": None}

    if state == "SUCCESS":
        result = task_result.result
        response["mission_id"] = result["mission_id"]
        response["outputs"] = {
            name: storage.presign_url(key)
            for name, key in result["output_keys"].items()
        }
    elif state == "FAILURE":
        response["outputs"] = {"error": str(task_result.info)}

    return response
