from contextlib import contextmanager
from collections.abc import Generator
from typing import IO

import boto3
from botocore.exceptions import ClientError

from autocrud.resource_manager.basic import (
    Encoding,
    IResourceStore,
    MsgspecSerializer,
)
from autocrud.types import RevisionInfo


class S3ResourceStore(IResourceStore):
    def __init__(
        self,
        encoding: Encoding = Encoding.json,
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
        self._resource_prefix = f"{self.prefix}resource/"
        self._store_prefix = f"{self.prefix}store/"
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
        self._info_serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=RevisionInfo,
        )

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

    def _get_raw_data_key(self, uid: str) -> str:
        """構建實際 data 文件的 S3 key"""
        return f"{self.prefix}store/{uid}/data"

    def _get_raw_info_key(self, uid: str) -> str:
        """構建實際 info 文件的 S3 key"""
        return f"{self.prefix}store/{uid}/info"

    def _get_resource_key(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> str:
        """構建資源索引的 S3 key"""
        if schema_version is None:
            p_schema_version = "no_ver"
        else:
            p_schema_version = f"v_{schema_version}"
        return (
            f"{self._resource_prefix}{resource_id}/{revision_id}/{p_schema_version}/uid"
        )

    def list_resources(self) -> Generator[str]:
        """列出所有資源 ID"""
        paginator = self.client.get_paginator("list_objects_v2")
        page_iterator = paginator.paginate(
            Bucket=self.bucket,
            Prefix=self._resource_prefix,
            Delimiter="/",
        )

        for page in page_iterator:
            if "CommonPrefixes" in page:
                for obj in page["CommonPrefixes"]:
                    prefix = obj["Prefix"]
                    # 去除前綴，然後移除末尾斜線，得到資源 ID
                    # 例如: "resources/resource/user1/" -> "user1"
                    resource_id = prefix[len(self._resource_prefix) :].rstrip("/")
                    if resource_id:
                        yield resource_id

    def list_revisions(self, resource_id: str) -> Generator[str]:
        """列出指定資源的所有修訂版本"""
        prefix = f"{self._resource_prefix}{resource_id}/"
        paginator = self.client.get_paginator("list_objects_v2")
        page_iterator = paginator.paginate(
            Bucket=self.bucket,
            Prefix=prefix,
            Delimiter="/",
        )

        for page in page_iterator:
            if "CommonPrefixes" in page:
                for obj in page["CommonPrefixes"]:
                    prefix_path = obj["Prefix"]
                    # 提取修訂 ID（去除前綴部分）
                    revision_id = prefix_path[len(prefix) :].rstrip("/")
                    if revision_id:  # 確保不是空字串
                        yield revision_id

    def list_schema_versions(
        self, resource_id: str, revision_id: str
    ) -> Generator[str | None]:
        """列出指定資源修訂版本的所有 schema 版本"""
        prefix = f"{self._resource_prefix}{resource_id}/{revision_id}/"
        paginator = self.client.get_paginator("list_objects_v2")
        page_iterator = paginator.paginate(
            Bucket=self.bucket,
            Prefix=prefix,
            Delimiter="/",
        )

        for page in page_iterator:
            if "CommonPrefixes" in page:
                for obj in page["CommonPrefixes"]:
                    prefix_path = obj["Prefix"]
                    # 提取 schema 版本（去除前綴部分）
                    schema_version = prefix_path[len(prefix) :].rstrip("/")
                    if schema_version == "no_ver":
                        yield None
                    elif schema_version.startswith("v_"):
                        yield schema_version[2:]
                    # else:  # 忽略不符合命名規則的資料夾
                    #     continue

    def exists(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> bool:
        """檢查指定的資源修訂版本是否存在"""
        resource_key = self._get_resource_key(resource_id, revision_id, schema_version)
        try:
            self.client.head_object(Bucket=self.bucket, Key=resource_key)
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("NoSuchKey", "404"):
                return False
            raise

    @contextmanager
    def get_data_bytes(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> Generator[IO[bytes]]:
        """以位元組流的形式獲取指定資源修訂版本的資料"""
        # 先獲取 UID
        resource_key = self._get_resource_key(resource_id, revision_id, schema_version)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=resource_key)
            uid = response["Body"].read().decode("utf-8")
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("NoSuchKey", "404"):
                raise KeyError(
                    f"Resource not found: {resource_id}/{revision_id}/{schema_version}"
                )
            raise

        # 使用 UID 獲取實際數據
        data_key = self._get_raw_data_key(uid)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=data_key)
            yield response["Body"]
            # data_bytes = response["Body"].read()
            # yield io.BytesIO(data_bytes)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("NoSuchKey", "404"):
                raise KeyError(f"Resource data not found: {uid}")
            raise

    def get_revision_info(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> RevisionInfo:
        """獲取指定修訂版本的資訊"""
        # 先獲取 UID
        resource_key = self._get_resource_key(resource_id, revision_id, schema_version)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=resource_key)
            uid = response["Body"].read().decode("utf-8")
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("NoSuchKey", "404"):
                raise KeyError(
                    f"Resource not found: {resource_id}/{revision_id}/{schema_version}"
                )
            raise

        # 使用 UID 獲取實際資訊
        info_key = self._get_raw_info_key(uid)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=info_key)
            info_bytes = response["Body"].read()
            return self._info_serializer.decode(info_bytes)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("NoSuchKey", "404"):
                raise KeyError(f"Revision info not found: {uid}")
            raise

    def save(self, info: RevisionInfo, data: IO[bytes]) -> None:
        # 保存實際數據和資訊到 UID-based 位置
        self._save_raw_data(str(info.uid), data)
        self._save_raw_info(info)
        # 建立資源索引，指向 UID
        self._create_resource_index(
            info.resource_id, info.revision_id, info.schema_version, str(info.uid)
        )

    def _save_raw_data(self, uid: str, data: IO[bytes]) -> None:
        """保存資源修訂版本的資料到 UID-based 位置"""
        data_key = self._get_raw_data_key(uid)
        self.client.put_object(Bucket=self.bucket, Key=data_key, Body=data.read())

    def _save_raw_info(self, info: RevisionInfo) -> None:
        """保存資源修訂版本的資訊到 UID-based 位置"""
        info_key = self._get_raw_info_key(str(info.uid))
        info_bytes = self._info_serializer.encode(info)
        self.client.put_object(Bucket=self.bucket, Key=info_key, Body=info_bytes)

    def _create_resource_index(
        self, resource_id: str, revision_id: str, schema_version: str | None, uid: str
    ) -> None:
        """建立資源索引，指向實際的 UID"""
        resource_key = self._get_resource_key(resource_id, revision_id, schema_version)
        self.client.put_object(
            Bucket=self.bucket, Key=resource_key, Body=uid.encode("utf-8")
        )

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
