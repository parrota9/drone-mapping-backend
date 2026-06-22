import os
import shutil
import tempfile
import time
import zipfile

from celery import current_task
from dotenv import load_dotenv
from pyodm import Node

import app.storage as storage
from app.core.config import ODM_HOST, ODM_PORT
from app.core.database import SessionLocal
from app.models.run import Run
from app.models.run_output import RunOutput
from app.worker.celery import celery_app

load_dotenv()


def _update_run(run_id: int, **kwargs):
    """Helper to update run fields in the DB"""
    db = SessionLocal()
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        for key, value in kwargs.items():
            setattr(run, key, value)
        db.commit()
    finally:
        db.close()


@celery_app.task(name="tasks.process_drone_mission")
def process_drone_mission(upload_key: str, run_id: int):
    tmp_dir = tempfile.mkdtemp(prefix=f"run_{run_id}_")
    zip_path = os.path.join(tmp_dir, "input.zip")
    extract_path = os.path.join(tmp_dir, "images")
    output_dir = os.path.join(tmp_dir, "outputs")

    try:
        _update_run(run_id, status="PROCESSING", progress=0.0)

        storage.download_file(upload_key, zip_path)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)

        image_files = []
        for root, _, files in os.walk(extract_path):
            for f in files:
                if f.lower().endswith((".png", ".jpg", ".jpeg")):
                    image_files.append(os.path.join(root, f))

        if not image_files:
            raise ValueError("No valid images found in the zip file.")

        print(f"Sending {len(image_files)} images to Node-ODM...")
        _update_run(run_id, status="PROCESSING", progress=5.0)

        node = Node(ODM_HOST, ODM_PORT)
        task = node.create_task(
            image_files, {"orthophoto": True, "orthophoto-png": True}
        )

        # Progress polling loop
        while True:
            info = task.info()
            if info.status.name == "COMPLETED":
                break
            if info.status.name == "FAILED":
                raise RuntimeError(f"ODM processing failed: {info.last_error}")

            progress = info.progress or 0.0
            _update_run(run_id, status="PROCESSING", progress=progress)
            current_task.update_state(state="PROGRESS", meta={"progress": progress})
            time.sleep(5)

        os.makedirs(output_dir, exist_ok=True)
        task.download_assets(output_dir)

        output_keys = storage.upload_directory(output_dir, f"completed/{run_id}")

        # Save outputs to DB
        db = SessionLocal()

        try:
            for output_type, minio_key in output_keys.items():
                db.add(
                    RunOutput(
                        run_id=run_id, output_type=output_type, minio_key=minio_key
                    )
                )
            db.commit()
        finally:
            db.close()

        _update_run(run_id, status="SUCCESS", progress=100.0)

        return {"status": "SUCCESS", "run_id": run_id}
    except Exception as e:
        _update_run(run_id, status="FAILED")
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
