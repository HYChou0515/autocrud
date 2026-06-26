from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

import msgspec
from msgspec import UNSET, Struct, UnsetType
from xxhash import xxh3_128, xxh3_128_hexdigest

from specstar.resource_manager.blob_store.simple import BasicBlobStore
from specstar.types import (
    Binary,
    BlobUploadSession,
)

try:
    from botocore.exceptions import ClientError as _ClientError
except ImportError:  # pragma: no cover
    _ClientError = None  # type: ignore[assignment,misc]  # ty:ignore[invalid-assignment]


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
    next_expected: int = 1  # eager-merge: next consecutive part number
    part_sizes: dict[
        str, int
    ] = {}  # {str(part_number): size} for accurate uploaded_size


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
        bucket: str = "specstar-blobs",
        prefix: str = "",
        upload_method: Literal["proxy", "single_put"] = "proxy",
        presigned_url_expiry: int = 3600,
        prefer_presigned_url: bool = False,
        client_kwargs: dict[str, Any] | None = None,
    ):
        import boto3

        self.bucket = bucket
        self.prefix = prefix
        self.upload_method = upload_method
        self.presigned_url_expiry = presigned_url_expiry
        self.prefer_presigned_url = prefer_presigned_url
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

    def _active_key(self, file_id: str) -> str:
        return f"{self.prefix}{file_id}"

    def _quarantine_key(self, file_id: str) -> str:
        return f"{self.prefix}_quarantine/{file_id}"

    def _refcount_key(self, file_id: str) -> str:
        return f"{self.prefix}_refcount/{file_id}"

    def get(self, file_id: str) -> Binary:
        # Active first (zero overhead on hit); on miss fall through to the
        # quarantine area so a transiently-quarantined blob is never lost (#370).
        for key in (self._active_key(file_id), self._quarantine_key(file_id)):
            try:
                response = self.client.get_object(Bucket=self.bucket, Key=key)
            except _ClientError as e:
                error_code = e.response.get("Error", {}).get("Code")
                if error_code in ("NoSuchKey", "404"):
                    continue
                raise
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
        raise FileNotFoundError(f"Blob {file_id} not found")

    def exists(self, file_id: str) -> bool:
        for key in (self._active_key(file_id), self._quarantine_key(file_id)):
            try:
                self.client.head_object(Bucket=self.bucket, Key=key)
                return True
            except _ClientError as e:
                error_code = e.response.get("Error", {}).get("Code")
                if error_code in ("404", "NoSuchKey"):
                    continue
                raise
        return False

    def delete(self, file_id: str) -> None:
        """Idempotently remove a blob (active or quarantined) and its refcount.
        S3 delete is already a no-op for a missing key."""
        for key in (
            self._active_key(file_id),
            self._quarantine_key(file_id),
            self._refcount_key(file_id),
        ):
            try:
                self.client.delete_object(Bucket=self.bucket, Key=key)
            except _ClientError:
                pass
        self._clear_candidate(file_id)

    def _read_refcount(self, file_id: str) -> int:
        try:
            resp = self.client.get_object(
                Bucket=self.bucket, Key=self._refcount_key(file_id)
            )
            return int(resp["Body"].read().decode())
        except _ClientError:
            return 0
        except ValueError:
            return 0

    def incref(self, file_id: str) -> int:
        n = self._read_refcount(file_id) + 1
        self.client.put_object(
            Bucket=self.bucket, Key=self._refcount_key(file_id), Body=str(n).encode()
        )
        self._note_count(file_id, n)
        return n

    def decref(self, file_id: str) -> int:
        n = max(0, self._read_refcount(file_id) - 1)
        self.client.put_object(
            Bucket=self.bucket, Key=self._refcount_key(file_id), Body=str(n).encode()
        )
        self._note_count(file_id, n)
        return n

    def get_mtime(self, file_id: str) -> dt.datetime | None:
        try:
            head = self.client.head_object(
                Bucket=self.bucket, Key=self._active_key(file_id)
            )
        except _ClientError:
            return None
        last_modified = head.get("LastModified")
        if last_modified is None:
            return None
        # boto returns an aware datetime; normalise to UTC.
        return last_modified.astimezone(dt.timezone.utc)

    def touch(self, file_id: str, *, now: dt.datetime | None = None) -> None:
        """Refresh ``LastModified`` via an in-place server-side self-copy.

        S3 sets ``LastModified`` to the server's current time on copy, so the
        ``now`` argument is accepted for API uniformity but not used as the
        stored stamp.  No-op if the blob is not active.
        """
        key = self._active_key(file_id)
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=key)
        except _ClientError:
            return
        copy_kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "CopySource": {"Bucket": self.bucket, "Key": key},
            "Key": key,
            "Metadata": head.get("Metadata", {}),
            "MetadataDirective": "REPLACE",
        }
        ct = head.get("ContentType")
        if ct:
            copy_kwargs["ContentType"] = ct
        try:
            self.client.copy_object(**copy_kwargs)
        except _ClientError:
            pass

    def iter_active(self):
        internal = ("_quarantine/", "_refcount/", "_sessions/", "_uploads/")
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
            for obj in page.get("Contents", []):
                rest = obj["Key"][len(self.prefix) :]
                if not rest or any(rest.startswith(p) for p in internal):
                    continue
                yield rest

    def quarantine(self, file_id: str, *, now: dt.datetime) -> None:
        """Move an active object into the quarantine prefix, recording ``now``
        in object metadata as the entry time. No-op if not active."""
        src = self._active_key(file_id)
        dst = self._quarantine_key(file_id)
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=src)
        except _ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                return
            raise
        copy_kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "CopySource": {"Bucket": self.bucket, "Key": src},
            "Key": dst,
            "Metadata": {"quarantine-entered": now.isoformat()},
            "MetadataDirective": "REPLACE",
        }
        ct = head.get("ContentType")
        if ct:
            copy_kwargs["ContentType"] = ct
        self.client.copy_object(**copy_kwargs)
        self.client.delete_object(Bucket=self.bucket, Key=src)
        self._clear_candidate(file_id)

    def restore_from_quarantine(self, file_id: str) -> None:
        """Move an object back from the quarantine prefix to active. No-op if absent."""
        src = self._quarantine_key(file_id)
        dst = self._active_key(file_id)
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=src)
        except _ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                return
            raise
        copy_kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "CopySource": {"Bucket": self.bucket, "Key": src},
            "Key": dst,
            "Metadata": {},
            "MetadataDirective": "REPLACE",
        }
        ct = head.get("ContentType")
        if ct:
            copy_kwargs["ContentType"] = ct
        self.client.copy_object(**copy_kwargs)
        self.client.delete_object(Bucket=self.bucket, Key=src)

    def iter_quarantined(self, *, entered_before: dt.datetime):
        """Yield file_ids quarantined strictly before ``entered_before``."""
        qprefix = f"{self.prefix}_quarantine/"
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=qprefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                file_id = key[len(qprefix) :]
                if not file_id:
                    continue
                head = self.client.head_object(Bucket=self.bucket, Key=key)
                entered_str = head.get("Metadata", {}).get("quarantine-entered")
                if entered_str is None:
                    continue
                if dt.datetime.fromisoformat(entered_str) < entered_before:
                    yield file_id

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

    def get_response(self, file_id: str):
        """Return the preferred download response for a blob.

        When ``prefer_presigned_url`` is ``True``, tries presigned URL
        redirect first (suitable when the client can reach S3 directly).
        Otherwise falls back to the default order:
        ``get_stream()`` → ``get()`` → ``get_url()``.
        """
        from specstar.types import BlobResponse

        if self.prefer_presigned_url:
            url = self.get_url(file_id)
            if url is not None:
                # Verify the blob exists (get_url may generate a URL
                # for a non-existent key depending on S3 implementation)
                if self.exists(file_id):
                    return BlobResponse("redirect", url=url)
            # Fall through to default strategy
        return super().get_response(file_id)

    def get_stream(self, file_id: str):
        """Stream blob content from S3 in 8 MB chunks (constant memory)."""
        from specstar.types import BlobStreamInfo

        key = f"{self.prefix}{file_id}"
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=key)
        except _ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchKey"):
                raise FileNotFoundError(f"Blob {file_id} not found")
            raise

        size = head.get("ContentLength", 0)
        content_type = head.get("ContentType", UNSET)
        if content_type is None:
            content_type = UNSET

        def _iterate():
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
            body = resp["Body"]
            while True:
                chunk = body.read(8 * 1024 * 1024)  # 8 MB
                if not chunk:
                    break
                yield chunk

        return BlobStreamInfo(
            _iterate(), size=size, content_type=content_type, file_id=file_id
        )

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
            status=meta.status,  # ty:ignore[invalid-argument-type]
            upload_method=meta.upload_method,  # ty:ignore[invalid-argument-type]
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

        # Track per-part size for accurate uploaded_size (handles retries)
        meta.part_sizes[str(part_number)] = len(data)
        meta.uploaded_size = sum(meta.part_sizes.values())

        if part_number not in meta.parts_received:
            meta.parts_received.append(part_number)
            meta.parts_received.sort()

        # Eager-merge tracking: advance next_expected through consecutive parts
        received_set = set(meta.parts_received)
        while meta.next_expected in received_set:
            meta.next_expected += 1

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
                MultipartUpload={"Parts": sorted_parts},  # ty:ignore[invalid-argument-type]
            )
        elif meta.status == "uploaded":
            # Legacy: single upload_to_session wrote to s3_key directly
            pass
        else:
            raise ValueError("No data uploaded to session")

        # Determine content type
        final_content_type: str | UnsetType = _ct_from_meta(meta.content_type)

        # Get size from the assembled object
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=meta.s3_key)
        except _ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                raise ValueError("Upload data not found in S3") from None
            raise
        size = head.get("ContentLength", 0)

        # Determine file_id
        if meta.key is not None:
            file_id = meta.key
            # Guess content type from object header if not provided
            if not final_content_type or final_content_type is UNSET:
                try:
                    resp = self.client.get_object(Bucket=self.bucket, Key=meta.s3_key)
                    header = resp["Body"].read(8192)
                    final_content_type = self.guess_content_type(header, UNSET)
                except _ClientError:
                    pass
        else:
            # Streaming hash — constant memory regardless of file size
            try:
                resp = self.client.get_object(Bucket=self.bucket, Key=meta.s3_key)
            except _ClientError as e:
                code = e.response.get("Error", {}).get("Code")
                if code in ("NoSuchKey", "404"):
                    raise ValueError("Upload data not found in S3") from None
                raise
            body = resp["Body"]
            hasher = xxh3_128()
            first = True
            while True:
                chunk = body.read(8 * 1024 * 1024)  # 8 MB chunks
                if not chunk:
                    break
                hasher.update(chunk)
                if first and (not final_content_type or final_content_type is UNSET):
                    final_content_type = self.guess_content_type(chunk, UNSET)
                    first = False
            file_id = hasher.hexdigest()

        # Move to final location via S3 server-side copy (no data through us)
        final_s3_key = f"{self.prefix}{file_id}"
        if meta.s3_key != final_s3_key:
            try:
                self.client.copy_object(
                    Bucket=self.bucket,
                    CopySource={"Bucket": self.bucket, "Key": meta.s3_key},
                    Key=final_s3_key,
                )
                self.client.delete_object(Bucket=self.bucket, Key=meta.s3_key)
            except _ClientError:
                pass

        meta.status = "finalized"
        self._save_session(meta)

        return Binary(
            file_id=file_id,
            size=size,
            content_type=final_content_type
            if (final_content_type and final_content_type is not UNSET)
            else UNSET,
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
