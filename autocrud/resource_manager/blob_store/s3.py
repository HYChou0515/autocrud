from __future__ import annotations

import uuid
from typing import Any, Literal

import msgspec
from msgspec import UNSET, Struct, UnsetType
from xxhash import xxh3_128_hexdigest

from autocrud.resource_manager.blob_store.simple import BasicBlobStore
from autocrud.types import Binary, BlobUploadSession

try:
    from botocore.exceptions import ClientError as _ClientError
except ImportError:  # pragma: no cover
    _ClientError = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Session metadata — persisted to S3 (HPA-safe)
# ---------------------------------------------------------------------------


class _S3SessionMeta(Struct, kw_only=True):
    """Session metadata stored in S3 for cross-instance persistence.

    Unlike an in-memory dict, this struct is serialised to a well-known
    S3 key so that *any* service instance sharing the same bucket/prefix
    can load the session — critical for HPA / multi-pod deployments.

    Upload data (proxy mode) is stored separately at ``s3_key``.
    """

    upload_id: str
    s3_key: str
    upload_method: str  # "proxy" | "single_put"
    status: str = "pending"  # pending | uploading | uploaded | finalized | aborted
    content_type: str | None = None  # None represents UNSET at the boundary
    size: int | None = None
    key: str | None = None  # caller-specified file_id key
    uploaded_size: int = 0
    multipart_upload_id: str | None = None  # S3 multipart upload ID
    parts: list[dict] = []  # [{"ETag": ..., "PartNumber": ...}]
    total_parts: int | None = None
    parts_received: list[int] = []  # sorted list of received part numbers


_meta_enc = msgspec.json.Encoder()
_meta_dec = msgspec.json.Decoder(_S3SessionMeta)


def _ct_to_meta(ct: str | UnsetType) -> str | None:
    """Convert public ``content_type`` (str | UNSET) to storage form (str | None)."""
    return ct if ct is not UNSET else None


def _ct_from_meta(ct: str | None) -> str | UnsetType:
    """Convert stored ``content_type`` (str | None) back to public form."""
    return ct if ct is not None else UNSET


class S3BlobStore(BasicBlobStore):
    """S3-backed blob store with upload sessions persisted to S3.

    Session metadata is stored in S3 at ``{prefix}_sessions/{upload_id}``
    as JSON, making it safe for multi-instance / HPA deployments.
    Upload data (proxy mode) or client-uploaded objects (single_put mode)
    are stored at ``{prefix}_uploads/{upload_id}``.

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

    # -- Session persistence helpers ------------------------------------

    def _session_meta_key(self, upload_id: str) -> str:
        """S3 key where session metadata JSON is stored."""
        return f"{self.prefix}_sessions/{upload_id}"

    def _save_session(self, meta: _S3SessionMeta) -> None:
        """Persist session metadata to S3."""
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._session_meta_key(meta.upload_id),
            Body=_meta_enc.encode(meta),
            ContentType="application/json",
        )

    def _load_session(self, upload_id: str) -> _S3SessionMeta:
        """Load session metadata from S3.

        Raises:
            FileNotFoundError: if the session does not exist.
        """
        try:
            resp = self.client.get_object(
                Bucket=self.bucket,
                Key=self._session_meta_key(upload_id),
            )
            return _meta_dec.decode(resp["Body"].read())
        except _ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                raise FileNotFoundError(
                    f"Upload session {upload_id} not found"
                ) from None
            raise

    # -- Upload session methods -------------------------------------------

    def create_upload_session(
        self,
        *,
        key: str | None = None,
        content_type: str | UnsetType = UNSET,
        size: int | None = None,
        total_parts: int | None = None,
    ) -> BlobUploadSession:
        upload_id = uuid.uuid4().hex
        file_id_placeholder = key or ""
        s3_key = f"{self.prefix}_uploads/{upload_id}"

        meta = _S3SessionMeta(
            upload_id=upload_id,
            s3_key=s3_key,
            upload_method=self.upload_method,
            content_type=_ct_to_meta(content_type),
            size=size,
            key=key,
            total_parts=total_parts,
        )

        if self.upload_method == "single_put":
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
            self._save_session(meta)
            return BlobUploadSession(
                upload_id=upload_id,
                file_id=file_id_placeholder,
                status="pending",
                upload_method="single_put",
                upload_url=upload_url,
                content_type=content_type,
                size=size,
                total_parts=total_parts,
            )

        # Proxy mode
        self._save_session(meta)
        return BlobUploadSession(
            upload_id=upload_id,
            file_id=file_id_placeholder,
            status="pending",
            upload_method="proxy",
            upload_url=f"/blobs/upload-sessions/{upload_id}/content",
            content_type=content_type,
            size=size,
            total_parts=total_parts,
        )

    def get_upload_session(self, upload_id: str) -> BlobUploadSession:
        meta = self._load_session(upload_id)
        return BlobUploadSession(
            upload_id=meta.upload_id,
            file_id=meta.key or "",
            status=meta.status,
            upload_method=meta.upload_method,
            content_type=_ct_from_meta(meta.content_type),
            size=meta.size,
            uploaded_size=meta.uploaded_size,
            total_parts=meta.total_parts,
            parts_received=list(meta.parts_received),
        )

    def upload_to_session(
        self, upload_id: str, data: bytes, *, part_number: int
    ) -> None:
        if part_number < 1:
            raise ValueError("part_number must be >= 1")
        meta = self._load_session(upload_id)
        if meta.upload_method == "single_put":
            raise NotImplementedError(
                "single_put mode: client uploads directly to S3 via presigned URL"
            )
        if meta.status not in ("pending", "uploading"):
            raise ValueError(
                f"Session status is '{meta.status}', expected 'pending' or 'uploading'"
            )

        # Lazy-init S3 multipart upload on first chunk
        if meta.multipart_upload_id is None:
            create_kwargs: dict[str, Any] = {
                "Bucket": self.bucket,
                "Key": meta.s3_key,
            }
            if meta.content_type:
                create_kwargs["ContentType"] = meta.content_type
            mpu = self.client.create_multipart_upload(**create_kwargs)
            meta.multipart_upload_id = mpu["UploadId"]
            meta.parts = []

        # Use caller-specified part_number (supports parallel & retry)
        resp = self.client.upload_part(
            Bucket=self.bucket,
            Key=meta.s3_key,
            UploadId=meta.multipart_upload_id,
            PartNumber=part_number,
            Body=data,
        )

        # Replace existing entry for this part_number (retry) or add new
        meta.parts = [p for p in meta.parts if p["PartNumber"] != part_number]
        meta.parts.append({"ETag": resp["ETag"], "PartNumber": part_number})

        meta.uploaded_size += len(data)
        if part_number not in meta.parts_received:
            meta.parts_received.append(part_number)
            meta.parts_received.sort()
        meta.status = "uploading"
        self._save_session(meta)

    def finalize_upload_session(self, upload_id: str) -> Binary:
        meta = self._load_session(upload_id)
        if meta.upload_method == "single_put":
            return self._finalize_single_put(meta)
        return self._finalize_proxy(meta)

    def _finalize_proxy(self, meta: _S3SessionMeta) -> Binary:
        """Finalize a proxy-mode session using S3 multipart upload."""
        if meta.status not in ("uploaded", "uploading"):
            raise ValueError(
                f"Session status is '{meta.status}', expected 'uploaded' or 'uploading'"
            )

        # Validate total_parts
        num_received = len(meta.parts_received)
        if meta.total_parts is not None and num_received != meta.total_parts:
            raise ValueError(
                f"Expected {meta.total_parts} parts but received {num_received}"
            )

        # Complete the S3 multipart upload (parts must be sorted by PartNumber)
        if meta.multipart_upload_id and meta.parts:
            sorted_parts = sorted(meta.parts, key=lambda p: p["PartNumber"])
            self.client.complete_multipart_upload(
                Bucket=self.bucket,
                Key=meta.s3_key,
                UploadId=meta.multipart_upload_id,
                MultipartUpload={"Parts": sorted_parts},
            )
        elif meta.status == "uploaded":
            # Legacy: single upload_to_session wrote to s3_key directly
            pass
        else:
            raise ValueError("No data uploaded to session")

        # Read the assembled object and store at final location via put()
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=meta.s3_key)
            data = resp["Body"].read()
        except _ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                raise ValueError("Upload data not found in S3") from None
            raise

        stored = self.put(
            data,
            key=meta.key,
            content_type=_ct_from_meta(meta.content_type),
        )

        meta.status = "finalized"
        self._save_session(meta)

        # Clean up temp upload key (best-effort, only if different from final)
        final_s3_key = f"{self.prefix}{stored.file_id}"
        if meta.s3_key != final_s3_key:
            try:
                self.client.delete_object(Bucket=self.bucket, Key=meta.s3_key)
            except _ClientError:
                pass

        return Binary(
            file_id=stored.file_id,
            size=stored.size,
            content_type=stored.content_type,
        )

    def _finalize_single_put(self, meta: _S3SessionMeta) -> Binary:
        """Finalize a single_put session: verify the object exists in S3."""
        if meta.status == "finalized":
            raise ValueError("Session has already been finalized")
        if meta.status == "aborted":
            raise ValueError("Session has been aborted")

        # Verify the client actually uploaded the object
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=meta.s3_key)
        except _ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "404" or error_code == "NoSuchKey":
                raise ValueError("Object not found in S3 — client has not uploaded yet")
            raise

        size = head.get("ContentLength", 0)
        content_type: str | UnsetType = head.get("ContentType", UNSET)

        if meta.key:
            final_s3_key = f"{self.prefix}{meta.key}"
            file_id = meta.key
        else:
            file_id = meta.upload_id
            final_s3_key = f"{self.prefix}{file_id}"

        # Move from temp upload key to final key (unless already there)
        if meta.s3_key != final_s3_key:
            self.client.copy_object(
                Bucket=self.bucket,
                CopySource={"Bucket": self.bucket, "Key": meta.s3_key},
                Key=final_s3_key,
            )
            self.client.delete_object(Bucket=self.bucket, Key=meta.s3_key)

        meta.status = "finalized"
        self._save_session(meta)

        return Binary(
            file_id=file_id,
            size=size,
            content_type=content_type if content_type else UNSET,
        )

    def abort_upload_session(self, upload_id: str) -> None:
        meta = self._load_session(upload_id)
        if meta.status == "finalized":
            raise ValueError("Cannot abort a finalized session")

        # Abort S3 multipart upload if one was started
        if meta.multipart_upload_id:
            try:
                self.client.abort_multipart_upload(
                    Bucket=self.bucket,
                    Key=meta.s3_key,
                    UploadId=meta.multipart_upload_id,
                )
            except _ClientError:
                pass

        # Clean up the temp S3 object (best-effort)
        if meta.upload_method == "single_put" or (
            meta.upload_method == "proxy" and meta.status in ("uploaded", "uploading")
        ):
            try:
                self.client.delete_object(Bucket=self.bucket, Key=meta.s3_key)
            except _ClientError:
                pass

        meta.status = "aborted"
        self._save_session(meta)
