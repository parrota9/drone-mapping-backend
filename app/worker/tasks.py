import os
import shutil
import tempfile
import zipfile

from celery import Celery, current_task
from dotenv import load_dotenv
from pyodm import Node

import storage

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ODM_HOST = os.getenv("ODM_HOST", "localhost")
ODM_PORT = int(os.getenv("ODM_PORT", "3000"))

celery_app = Celery("drone_tasks", broker=REDIS_URL, backend=REDIS_URL)


@celery_app.task(name="tasks.process_drone_mission")
def process_drone_mission(upload_key: str, mission_id: str):
    tmp_dir = tempfile.mkdtemp(prefix=f"mission_{mission_id}_")
    zip_path = os.path.join(tmp_dir, "input.zip")
    extract_path = os.path.join(tmp_dir, "images")
    output_dir = os.path.join(tmp_dir, "outputs")

    try:
        storage.download_file(upload_key, zip_path)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)

        image_files = []
        for root, _, files in os.walk(extract_path):
            for f in files:
                if f.lower().endswith((".png", ".jpg", ".jpeg")):
                    image_files.append(os.path.join(root, f))

        if not image_files:
            return {"status": "FAILED", "error": "No valid images found in zip file."}

        print(f"Sending {len(image_files)} images to Node-ODM engine...")

        node = Node(ODM_HOST, ODM_PORT)
        task = node.create_task(
            image_files, {"orthophoto": True, "orthophoto-png": True}
        )
        task.wait_for_completion()

        os.makedirs(output_dir, exist_ok=True)
        task.download_assets(output_dir)

        output_keys = storage.upload_directory(output_dir, f"completed/{mission_id}")

        return {
            "status": "SUCCESS",
            "mission_id": mission_id,
            "output_keys": output_keys,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
