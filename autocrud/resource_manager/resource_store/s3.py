import io
from collections.abc import Generator
from typing import TypeVar

import boto3
from botocore.exceptions import ClientError

from autocrud.resource_manager.basic import (
    Encoding,
    IResourceStore,
    MsgspecSerializer,
)
from autocrud.types import IMigration, Resource, RevisionInfo

T = TypeVar("T")


class S3ResourceStore(IResourceStore[T]):
    def __init__(
        self,
        resource_type: type[T],
        encoding: Encoding = Encoding.json,
        migration: IMigration | None = None,
        access_key_id: str = "minioadmin",
        secret_access_key: str = "minioadmin",
        region_name: str = "us-east-1",
        endpoint_url: str | None = None,  # minio example:  "http://localhost:9000"
        bucket: str = "autocrud",
        prefix: str = "",
        client_kwargs: dict | None = None,
    ):
        self.bucket = bucket
        self.prefix = f"{prefix}resources/"
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
        self._data_serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=resource_type,
        )
        self._info_serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=RevisionInfo,
        )
        self.migration = migration

        # 確保 bucket 存在
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            # 檢查是否是 NoSuchBucket 錯誤 (支援 AWS 和 MinIO)
            error_code = e.response["Error"]["Code"]
            if error_code in ("NoSuchBucket", "404"):
                self.client.create_bucket(Bucket=self.bucket)
            else:
                # 其他錯誤則重新拋出
                raise

    def _get_data_key(self, resource_id: str, revision_id: str) -> str:
        """構建 data 文件的 S3 key"""
        return f"{self.prefix}{resource_id}/data/{revision_id}"

    def _get_info_key(self, resource_id: str, revision_id: str) -> str:
        """構建 info 文件的 S3 key"""
        return f"{self.prefix}{resource_id}/info/{revision_id}"

    def list_resources(self) -> Generator[str]:
        """列出所有資源 ID"""
        paginator = self.client.get_paginator("list_objects_v2")
        page_iterator = paginator.paginate(
            Bucket=self.bucket,
            Prefix=self.prefix,
            Delimiter="/",
        )

        for page in page_iterator:
            if "CommonPrefixes" in page:
                for obj in page["CommonPrefixes"]:
                    prefix = obj["Prefix"]
                    # 去除前綴，然後移除末尾斜線，得到資源 ID
                    # 例如: "resources/user1/" -> "user1"
                    resource_id = prefix[len(self.prefix) :].rstrip("/")
                    if resource_id:
                        yield resource_id

    def list_revisions(self, resource_id: str) -> Generator[str]:
        """列出指定資源的所有修訂版本"""
        prefix = f"{self.prefix}{resource_id}/info/"
        paginator = self.client.get_paginator("list_objects_v2")
        page_iterator = paginator.paginate(
            Bucket=self.bucket,
            Prefix=prefix,
        )

        for page in page_iterator:
            if "Contents" in page:
                for obj in page["Contents"]:
                    key = obj["Key"]
                    # 提取修訂 ID（去除前綴部分）
                    revision_id = key[len(prefix) :]
                    if revision_id:  # 確保不是空字串
                        yield revision_id

    def exists(self, resource_id: str, revision_id: str) -> bool:
        """檢查指定的資源修訂版本是否存在"""
        info_key = self._get_info_key(resource_id, revision_id)
        try:
            self.client.head_object(Bucket=self.bucket, Key=info_key)
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("NoSuchKey", "404"):
                return False
            raise

    def get(self, resource_id: str, revision_id: str) -> Resource[T]:
        """獲取指定的資源修訂版本"""
        info = self.get_revision_info(resource_id, revision_id)
        data_key = self._get_data_key(resource_id, revision_id)

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=data_key)
            data_bytes = response["Body"].read()

            if (
                self.migration is None
                or info.schema_version == self.migration.schema_version
            ):
                data = self._data_serializer.decode(data_bytes)
            else:
                # 執行資料遷移
                data_io = io.BytesIO(data_bytes)
                data = self.migration.migrate(data_io, info.schema_version)
                info.schema_version = self.migration.schema_version

                # 更新 info 和 data 存儲
                info_key = self._get_info_key(resource_id, revision_id)
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=info_key,
                    Body=self._info_serializer.encode(info),
                )

                migrated_data_bytes = self._data_serializer.encode(data)
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=data_key,
                    Body=migrated_data_bytes,
                )

            return Resource(
                info=info,
                data=data,
            )
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("NoSuchKey", "404"):
                raise KeyError(f"Resource data not found: {resource_id}/{revision_id}")
            raise

    def get_revision_info(self, resource_id: str, revision_id: str) -> RevisionInfo:
        """獲取指定修訂版本的資訊"""
        info_key = self._get_info_key(resource_id, revision_id)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=info_key)
            info_bytes = response["Body"].read()
            return self._info_serializer.decode(info_bytes)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("NoSuchKey", "404"):
                raise KeyError(f"Revision info not found: {resource_id}/{revision_id}")
            raise

    def save(self, data: Resource[T]) -> None:
        """保存資源修訂版本"""
        resource_id = data.info.resource_id
        revision_id = data.info.revision_id

        # 保存資料
        data_key = self._get_data_key(resource_id, revision_id)
        data_bytes = self._data_serializer.encode(data.data)
        self.client.put_object(Bucket=self.bucket, Key=data_key, Body=data_bytes)

        # 保存資訊
        info_key = self._get_info_key(resource_id, revision_id)
        info_bytes = self._info_serializer.encode(data.info)
        self.client.put_object(Bucket=self.bucket, Key=info_key, Body=info_bytes)

    def encode(self, data: T) -> bytes:
        """編碼資料為位元組"""
        return self._data_serializer.encode(data)

    def cleanup(self) -> None:
        """清理所有以指定前綴開頭的 S3 物件"""
        paginator = self.client.get_paginator("list_objects_v2")
        page_iterator = paginator.paginate(Bucket=self.bucket, Prefix=self.prefix)

        objects_to_delete = []
        for page in page_iterator:
            if "Contents" in page:
                for obj in page["Contents"]:
                    objects_to_delete.append({"Key": obj["Key"]})

        # 批量刪除物件
        if objects_to_delete:
            # S3 批量刪除每次最多1000個物件
            for i in range(0, len(objects_to_delete), 1000):
                batch = objects_to_delete[i : i + 1000]
                self.client.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": batch},
                )
