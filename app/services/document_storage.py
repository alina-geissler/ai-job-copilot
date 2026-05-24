"""Provide object storage operations for document files.

Wrap the boto3 S3 client to upload, delete, and generate presigned URLs
for documents stored in MinIO or AWS S3. All operations use the same
interface regardless of the backend — only the endpoint URL differs.
"""

from __future__ import annotations

import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_storage_client():
    """Create and return a configured boto3 S3 client.

    Connect to MinIO when ``STORAGE_ENDPOINT_URL`` is set, or fall back to
    standard AWS S3 when it is absent.

    :return: Configured boto3 S3 client.
    """
    kwargs: dict = {
        "aws_access_key_id": settings.storage_access_key,
        "aws_secret_access_key": settings.storage_secret_key,
        "region_name": settings.storage_region,
    }
    if settings.storage_endpoint_url:
        kwargs["endpoint_url"] = settings.storage_endpoint_url
    return boto3.client("s3", **kwargs)


def upload_document(*, storage_key: str, file_bytes: bytes, mime_type: str) -> None:
    """Upload a document to the configured storage bucket.

    :param storage_key: Destination key within the bucket.
    :param file_bytes: Raw file content to upload.
    :param mime_type: MIME type to store as the object's ContentType.
    :raises RuntimeError: If the upload fails due to a storage error.
    """
    client = get_storage_client()
    try:
        client.put_object(
            Bucket=settings.storage_bucket_name,
            Key=storage_key,
            Body=file_bytes,
            ContentType=mime_type,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.error("Storage upload failed for key %r: %s", storage_key, exc)
        raise RuntimeError(f"Storage upload failed: {exc}") from exc


def download_document(*, storage_key: str) -> bytes:
    """Download a document from the configured storage bucket.

    :param storage_key: Key of the object to download.
    :return: Raw file bytes.
    :raises RuntimeError: If the download fails due to a storage error.
    """
    client = get_storage_client()
    try:
        response = client.get_object(
            Bucket=settings.storage_bucket_name,
            Key=storage_key,
        )
        return response["Body"].read()
    except (BotoCoreError, ClientError) as exc:
        logger.error("Storage download failed for key %r: %s", storage_key, exc)
        raise RuntimeError(f"Storage download failed: {exc}") from exc


def generate_presigned_url(*, storage_key: str, expires_in: int = 900) -> str:
    """Generate a temporary presigned URL to download a document.

    :param storage_key: Key of the object in the bucket.
    :param expires_in: URL lifetime in seconds (default 15 minutes).
    :return: Presigned URL string.
    :raises RuntimeError: If the URL cannot be generated.
    """
    client = get_storage_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.storage_bucket_name, "Key": storage_key},
            ExpiresIn=expires_in,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.error("Presigned URL generation failed for key %r: %s", storage_key, exc)
        raise RuntimeError(f"Presigned URL generation failed: {exc}") from exc


def delete_document(*, storage_key: str) -> None:
    """Delete a document from the configured storage bucket.

    Log a warning on failure but do not raise — a failed storage delete
    should not prevent the database record from being removed.

    :param storage_key: Key of the object to delete.
    """
    client = get_storage_client()
    try:
        client.delete_object(
            Bucket=settings.storage_bucket_name,
            Key=storage_key,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.warning("Storage delete failed for key %r: %s", storage_key, exc)
