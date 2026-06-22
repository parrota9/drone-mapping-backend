import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

import app.storage as storage
from app.core.database import get_db
from app.models.mission import Mission
from app.models.run import Run
from app.models.run_output import RunOutput
from app.worker.tasks import process_drone_mission

router = APIRouter()


@router.post("/maps/process")
async def upload_and_stitch_map(
    file: UploadFile = File(...), db: Session = Depends(get_db)
):
    if not file.filename.endswith(".zip"):
        raise HTTPException(
            status_code=400, detail="Only compressed .zip folders are supported."
        )

    # Create mission from filename
    mission_name = os.path.splitext(file.filename)[0]
    mission = Mission(user_id=1, name=mission_name)  # user_id=1 for single-user
    db.add(mission)
    db.flush()  # get mission.id without committing yet

    # Create run record
    run = Run(mission_id=mission.id, status="PENDING")
    db.add(run)
    db.flush()  # get run.id

    # Upload zip to MinIO
    upload_key = f"uploads/{run.id}/{file.filename}"
    storage.upload_fileobj(file.file, upload_key)

    # Queue Celery task
    task = process_drone_mission.apply_async(
        args=[upload_key, run.id], task_id=str(uuid.uuid4())
    )

    # Save celery task id to run
    run.celery_task_id = task.id
    db.commit()

    return {
        "message": "Drone mission queued for processing.",
        "mission_id": mission.id,
        "mission_name": mission.name,
        "run_id": run.id,
        "task_id": task.id,
        "status": "PENDING",
    }


@router.get("/maps/status/{run_id}")
async def get_processing_status(run_id: int, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")

    response = {
        "run_id": run.id,
        "mission_id": run.mission_id,
        "status": run.status,
        "progress": run.progress,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "outputs": None,
    }

    if run.status == "SUCCESS":
        outputs = db.query(RunOutput).filter(RunOutput.run_id == run.id).all()
        response["outputs"] = {
            o.output_type: storage.presign_url(o.minio_key) for o in outputs
        }

    return response
