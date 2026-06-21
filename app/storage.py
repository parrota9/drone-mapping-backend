import os

import boto3
from dotenv import load_dotenv
from botocore.client import Config
from botocore.exceptions import ClientError

load_dotenv()

BUCKET = "drone-missions"
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")

# Maps a friendly output name to a predicate that matches its MinIO key.
# Only the first match per name is kept, so order matters for ambiguous patterns.
_OUTPUT_PATTERNS = {
    "orthophoto_tif": lambda k: k.endswith("odm_orthophoto.tif"),
    "orthophoto_png": lambda k: k.endswith("odm_orthophoto.png"),
    "dsm":            lambda k: k.endswith("dsm.tif"),
    "dtm":            lambda k: k.endswith("dtm.tif"),
    "point_cloud":    lambda k: k.endswith(".laz") or k.endswith(".las"),
    "report":         lambda k: "odm_report" in k and k.endswith(".pdf"),
}


def _client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ensure_bucket():
    client = _client()
    try:
        client.head_bucket(Bucket=BUCKET)
    except ClientError:
        client.create_bucket(Bucket=BUCKET)


def upload_fileobj(fileobj, key: str) -> str:
    _client().upload_fileobj(fileobj, BUCKET, key)
    return key


def download_file(key: str, local_path: str):
    parent = os.path.dirname(local_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    _client().download_file(BUCKET, key, local_path)


def upload_directory(local_dir: str, prefix: str) -> dict:
    """Upload every file under local_dir and return a dict of {output_name: key}
    for any file that matches a known ODM output pattern."""
    client = _client()
    output_keys = {}
    for root, _, files in os.walk(local_dir):
        for filename in files:
            local_path = os.path.join(root, filename)
            relative = os.path.relpath(local_path, local_dir).replace("\\", "/")
            key = f"{prefix}/{relative}"
            client.upload_file(local_path, BUCKET, key)
            for name, matches in _OUTPUT_PATTERNS.items():
                if name not in output_keys and matches(key):
                    output_keys[name] = key
    return output_keys


def presign_url(key: str, expiry: int = 3600) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": key},
        ExpiresIn=expiry,
    )
