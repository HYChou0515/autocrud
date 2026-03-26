from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from msgspec import UNSET, UnsetType
from xxhash import xxh3_128_hexdigest

from autocrud.resource_manager.blob_store.simple import BasicBlobStore
from autocrud.types import Binary, BlobUploadSession

try:
    from botocore.exceptions import ClientError as _ClientError
except ImportError:  # pragma: no cover
    _ClientError = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Internal session state
# ---------------------------------------------------------------------------


@dataclass
class _S3UploadSessionState:
    """In-memory state for an S3 upload session."""

    upload_id: str
    s3_key: str
    upload_method: Literal["proxy", "single_put"]
    status: str = "pending"  # pending | uploaded | finalized | aborted
    content_type: str | UnsetType = UNSET
    size: int | None = None
    key: str | None = None  # caller-specified file_id key
    data: bytes | None = None  # buffered bytes (proxy mode only)


class S3BlobStore(BasicBlobStore):
    """S3-backed blob store with optional presigned-URL upload sessions.

    Args:
        access_key_id: AWS access key (default ``"minioadmin"`` for MinIO).
        secret_access_key: AWS secret key (default ``"minioadmin"`` for MinIO).
        region_name: AWS region (default ``"us-east-1"``).
        endpoint_url: S3 endpoint URL (use for MinIO / S3-compatible).
        bucket: S3 bucket name.
        prefix: Key prefix for all objects.
        upload_method: How upload sessions deliver bytes:
            ``"proxy"`` (default) — bytes flow through the server;
            ``"single_put"`` — a presigned PUT URL is returned so the
            client uploads directly to S3.
        presigned_url_expiry: Expiry in seconds for presigned URLs
            (default ``3600``).
        client_kwargs: Extra kwargs forwarded to ``boto3.client()``.
    """

    def __init__(
        self,
        access_key_id: str = "minioadmin",
        secret_access_key: str = "minioadmin",
        region_name: str = "us-east-1",
        endpoint_url: str | None = None,
        bucket: str = "autocrud-blobs",
        prefix: str = "",
        upload_method: Literal["proxy", "single_put"] = "proxy",
        presigned_url_expiry: int = 3600,
        client_kwargs: dict[str, Any] | None = None,
    ):
        import boto3

        self.bucket = bucket
        self.prefix = prefix
        self.upload_method = upload_method
        self.presigned_url_expiry = presigned_url_expiry
        if client_kwargs is None:
            client_kwargs = {}
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region_name,
            **client_kwargs,
        )

        try:
            self.client.head_bucket(Bucket=self.bucket)
        except _ClientError as e:
            # Check for both 404 (Not Found) AND NoSuchBucket
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "404" or error_code == "NoSuchBucket":
                self.client.create_bucket(Bucket=self.bucket)
            else:
                raise

        self._sessions: dict[str, _S3UploadSessionState] = {}

    def put(
        self,
        data: bytes,
        *,
        key: str | None = None,
        content_type: str | UnsetType = UNSET,
    ) -> Binary:
        file_id = key if key is not None else xxh3_128_hexdigest(data)
        s3_key = f"{self.prefix}{file_id}"

        kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": s3_key,
            "Body": data,
        }
        content_type_ = self.guess_content_type(data, content_type)
        if content_type_:
            kwargs["ContentType"] = content_type_

        self.client.put_object(**kwargs)
        return Binary(
            file_id=file_id,
            size=len(data),
            data=data,
            content_type=content_type_ if content_type_ else UNSET,
        )

    def get(self, file_id: str) -> Binary:
        key = f"{self.prefix}{file_id}"
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            content = response["Body"].read()
            content_type = response.get("ContentType")
            if content_type is None:
                content_type = UNSET
            return Binary(
                file_id=file_id,
                size=len(content),
                data=content,
                content_type=content_type,
            )
        except _ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "NoSuchKey":
                raise FileNotFoundError(f"Blob {file_id} not found")
            raise

    def exists(self, file_id: str) -> bool:
        key = f"{self.prefix}{file_id}"
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except _ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "404" or error_code == "NoSuchKey":
                return False
            raise

    def get_url(self, file_id: str) -> str | None:
        key = f"{self.prefix}{file_id}"
        try:
            url = self.client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=self.presigned_url_expiry,
            )
            return url
        except _ClientError:
            return None

    # -- Upload session methods -------------------------------------------

    def create_upload_session(
        self,
        *,
        key: str | None = None,
        content_type: str | UnsetType = UNSET,
        size: int | None = None,
    ) -> BlobUploadSession:
        upload_id = uuid.uuid4().hex
        # Use the caller key or a temporary key based on upload_id
        file_id_placeholder = key or ""
        s3_key = f"{self.prefix}_uploads/{upload_id}"

        state = _S3UploadSessionState(
            upload_id=upload_id,
            s3_key=s3_key,
            upload_method=self.upload_method,
            content_type=content_type,
            size=size,
            key=key,
        )

        if self.upload_method == "single_put":
            # Generate presigned PUT URL for direct client upload
            params: dict[str, Any] = {
                "Bucket": self.bucket,
                "Key": s3_key,
            }
            if content_type and content_type is not UNSET:
                params["ContentType"] = content_type
            upload_url = self.client.generate_presigned_url(
                ClientMethod="put_object",
                Params=params,
                ExpiresIn=self.presigned_url_expiry,
            )
            self._sessions[upload_id] = state
            return BlobUploadSession(
                upload_id=upload_id,
                file_id=file_id_placeholder,
                status="pending",
                upload_method="single_put",
                upload_url=upload_url,
                content_type=content_type,
                size=size,
            )

        # Proxy mode
        self._sessions[upload_id] = state
        return BlobUploadSession(
            upload_id=upload_id,
            file_id=file_id_placeholder,
            status="pending",
            upload_method="proxy",
            upload_url=f"/blobs/upload-sessions/{upload_id}/content",
            content_type=content_type,
            size=size,
        )

    def get_upload_session(self, upload_id: str) -> BlobUploadSession:
        state = self._sessions.get(upload_id)
        if state is None:
            raise FileNotFoundError(f"Upload session {upload_id} not found")
        return BlobUploadSession(
            upload_id=state.upload_id,
            file_id=state.key or "",
            status=state.status,
            upload_method=state.upload_method,
            content_type=state.content_type,
            size=state.size,
        )

    def upload_to_session(self, upload_id: str, data: bytes) -> None:
        state = self._sessions.get(upload_id)
        if state is None:
            raise FileNotFoundError(f"Upload session {upload_id} not found")
        if state.upload_method == "single_put":
            raise NotImplementedError(
                "single_put mode: client uploads directly to S3 via presigned URL"
            )
        if state.status != "pending":
            raise ValueError(f"Session status is '{state.status}', expected 'pending'")
        state.data = data
        state.size = len(data)
        state.status = "uploaded"

    def finalize_upload_session(self, upload_id: str) -> Binary:
        state = self._sessions.get(upload_id)
        if state is None:
            raise FileNotFoundError(f"Upload session {upload_id} not found")

        if state.upload_method == "single_put":
            return self._finalize_single_put(state)
        return self._finalize_proxy(state)

    def _finalize_proxy(self, state: _S3UploadSessionState) -> Binary:
        """Finalize a proxy-mode session: put buffered bytes to S3."""
        if state.status != "uploaded":
            raise ValueError(f"Session status is '{state.status}', expected 'uploaded'")
        stored = self.put(
            state.data,  # type: ignore[arg-type]
            key=state.key,
            content_type=state.content_type,
        )
        state.status = "finalized"
        state.data = None
        return Binary(
            file_id=stored.file_id,
            size=stored.size,
            content_type=stored.content_type,
        )

    def _finalize_single_put(self, state: _S3UploadSessionState) -> Binary:
        """Finalize a single_put session: verify the object exists in S3."""
        if state.status == "finalized":
            raise ValueError("Session has already been finalized")
        if state.status == "aborted":
            raise ValueError("Session has been aborted")

        # Verify the client actually uploaded the object
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=state.s3_key)
        except _ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "404" or error_code == "NoSuchKey":
                raise ValueError("Object not found in S3 — client has not uploaded yet")
            raise

        size = head.get("ContentLength", 0)
        content_type: str | UnsetType = head.get("ContentType", UNSET)

        # If a caller key was provided, copy to the final location;
        # otherwise use the upload_id as file_id.
        if state.key:
            final_s3_key = f"{self.prefix}{state.key}"
            file_id = state.key
        else:
            file_id = state.upload_id
            final_s3_key = f"{self.prefix}{file_id}"

        # Move from temp upload key to final key (unless already there)
        if state.s3_key != final_s3_key:
            self.client.copy_object(
                Bucket=self.bucket,
                CopySource={"Bucket": self.bucket, "Key": state.s3_key},
                Key=final_s3_key,
            )
            self.client.delete_object(Bucket=self.bucket, Key=state.s3_key)

        state.status = "finalized"
        return Binary(
            file_id=file_id,
            size=size,
            content_type=content_type if content_type else UNSET,
        )

    def abort_upload_session(self, upload_id: str) -> None:
        state = self._sessions.get(upload_id)
        if state is None:
            raise FileNotFoundError(f"Upload session {upload_id} not found")
        if state.status == "finalized":
            raise ValueError("Cannot abort a finalized session")

        # For single_put, try to clean up the S3 object
        if state.upload_method == "single_put":
            try:
                self.client.delete_object(Bucket=self.bucket, Key=state.s3_key)
            except _ClientError:
                pass  # best-effort cleanup

        state.data = None
        state.status = "aborted"
