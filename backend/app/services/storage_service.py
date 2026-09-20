"""对象存储服务（MinIO）。"""

from io import BytesIO
from typing import BinaryIO

from minio import Minio
from minio.error import S3Error

from app.config import settings


class StorageService:
    """MinIO 封装，支持服务端加密。"""

    def __init__(self):
        self.client = Minio(
            f"{settings.minio_host}:{settings.minio_port}",
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=False,
        )
        self._ensure_buckets()

    def _ensure_buckets(self) -> None:
        """确保所有业务桶存在。"""
        for bucket in [
            settings.minio_bucket_invoice,
            settings.minio_bucket_contract,
            settings.minio_bucket_kb,
        ]:
            try:
                if not self.client.bucket_exists(bucket):
                    self.client.make_bucket(bucket)
            except S3Error:
                # 已存在或网络问题
                pass

    def upload_file(
        self,
        bucket: str,
        object_name: str,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
    ) -> str:
        """上传文件，返回对象 URL。"""
        if isinstance(data, bytes):
            data = BytesIO(data)
        self.client.put_object(
            bucket_name=bucket,
            object_name=object_name,
            data=data,
            length=-1,
            part_size=10 * 1024 * 1024,
            content_type=content_type,
        )
        return f"s3://{bucket}/{object_name}"

    def get_presigned_url(self, bucket: str, object_name: str, expires: int = 3600) -> str:
        """生成临时下载 URL。"""
        from datetime import timedelta

        return self.client.presigned_get_object(
            bucket_name=bucket,
            object_name=object_name,
            expires=timedelta(seconds=expires),
        )

    def delete_file(self, bucket: str, object_name: str) -> None:
        """删除文件。"""
        self.client.remove_object(bucket, object_name)


storage_service = StorageService()