from typing import Any

import boto3
from botocore.exceptions import ClientError
from xxhash import xxh3_128_hexdigest

from autocrud.resource_manager.basic import IBlobStore
from autocrud.types import Binary


class S3BlobStore(IBlobStore):
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

    def put(self, data: bytes) -> str:
        file_id = xxh3_128_hexdigest(data)
        key = f"{self.prefix}{file_id}"
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
        )
        return file_id

    def get(self, file_id: str) -> Binary:
        key = f"{self.prefix}{file_id}"
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            content = response["Body"].read()
            return Binary(file_id=file_id, size=len(content), data=content)
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
