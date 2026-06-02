import os
import zipfile
from platform import node

from celery import Celery
from pyodm import Node

# Connect Celery to the Redis container running via Docker
celery_app = Celery(
    "drone_tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0"
)


@celery_app.task(name="tasks.process_drone_mission")
def process_drone_mission(zip_file_path: str, output_dir: str):
    node = Node("localhost", 3000)

    # Extract the uploaded zip file containing the images
    extract_path = zip_file_path.replace(".zip", "_extracted")
    with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
        zip_ref.extractall(extract_path)

    # Gather all JPEG/PNG images recursively from the extracted directory and subdirectories
    image_files = []
    for root, dirs, files in os.walk(extract_path):
        for f in files:
            if f.lower().endswith((".png", ".jpg", ".jpeg")):
                image_files.append(os.path.join(root, f))

    if not image_files:
        print(f"Extraction paths checked, but zero images found in: {extract_path}")
        return {"status": "FAILED", "error": "No valid images found in zip file."}

    print(f"Sending {len(image_files)} images to Node-ODM engine...")

    # Start the photogrammetry task
    task = node.create_task(image_files, {"orthophoto": True, "orthophoto-png": True})

    # This blocks the Celery worker thread while monitoring the Docker node's progress
    task.wait_for_completion()

    # Download all the output assets
    os.makedirs(output_dir, exist_ok=True)
    task.download_assets(output_dir)

    print(f"Mission complete! Stitched assets saved to {output_dir}")
    return {"status": "SUCCESS", "output_directory": output_dir}
