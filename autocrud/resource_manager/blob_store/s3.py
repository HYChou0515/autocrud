from typing import Any

import boto3
from botocore.exceptions import ClientError
from msgspec import UNSET, UnsetType
from xxhash import xxh3_128_hexdigest

from autocrud.resource_manager.blob_store.simple import BasicBlobStore
from autocrud.types import Binary


class S3BlobStore(BasicBlobStore):
    def __init__(
        self,
        access_key_id: str = "minioadmin",
        secret_access_key: str = "minioadmin",
        region_name: str = "us-east-1",
        endpoint_url: str | None = None,
        bucket: str = "autocrud-blobs",
        prefix: str = "",
        client_kwargs: dict[str, Any] | None = None,
    ):
        self.bucket = bucket
        self.prefix = prefix
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
        except ClientError as e:
            # Check for both 404 (Not Found) AND NoSuchBucket
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "404" or error_code == "NoSuchBucket":
                self.client.create_bucket(Bucket=self.bucket)
            else:
                raise

    def put(self, data: bytes, *, content_type: str | UnsetType = UNSET) -> Binary:
        file_id = xxh3_128_hexdigest(data)
        key = f"{self.prefix}{file_id}"

        kwargs = {
            "Bucket": self.bucket,
            "Key": key,
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
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "NoSuchKey":
                raise FileNotFoundError(f"Blob {file_id} not found")
            raise

    def exists(self, file_id: str) -> bool:
        key = f"{self.prefix}{file_id}"
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "404" or error_code == "NoSuchKey":
                return False
            raise

    def get_url(self, file_id: str) -> str | None:
        key = f"{self.prefix}{file_id}"
        try:
            # Check if exists first? Or just generate the URL?
            # Usually presigned URL generation is offline operation (doesn't check existence).
            # But the route template will handle 404 if the client tries to use the URL.
            # However, if we want strict consistency, we might check exists.
            # But 'get_url' is usually expected to be fast.
            # If the file doesn't exist, the redirect will lead to a 404 from S3, which is fine.

            url = self.client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=3600,
            )
            return url
        except ClientError:
            return None
