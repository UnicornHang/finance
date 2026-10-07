"""对象存储服务（MinIO），SSE-S3 服务端加密。"""

from collections.abc import Mapping
from datetime import timedelta
from io import BytesIO
import logging
from typing import BinaryIO

from minio import Minio
from minio.error import S3Error
from minio.sse import SseS3
from minio.sseconfig import Rule, SSEConfig

from app.config import settings

logger = logging.getLogger(__name__)

_SSE_HEADER = "x-amz-server-side-encryption"


def object_encrypted_sse_s3(stat: object) -> bool:
    """stat_object 结果是否已是 SSE-S3（AES256）。"""
    meta = getattr(stat, "metadata", None) or {}
    # MinIO stat_object.metadata 常为 urllib3 HTTPHeaderDict（Mapping 而非 dict）
    if not isinstance(meta, Mapping):
        return False
    for key, value in meta.items():
        if str(key).lower() == _SSE_HEADER and str(value).upper() == "AES256":
            return True
    return False


class StorageService:
    """MinIO 封装：桶默认 SSE-S3，上传显式带 SseS3。"""

    def __init__(self):
        self.client = Minio(
            f"{settings.minio_host}:{settings.minio_port}",
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=False,
        )
        self._ensure_buckets()

    def _business_buckets(self) -> list[str]:
        """发票 / 合同 / 知识库（对话附件也在 kb 桶）。"""
        return [
            settings.minio_bucket_invoice,
            settings.minio_bucket_contract,
            settings.minio_bucket_kb,
        ]

    def _ensure_buckets(self) -> None:
        """确保业务桶存在并打开默认 SSE-S3。"""
        for bucket in self._business_buckets():
            try:
                if not self.client.bucket_exists(bucket):
                    self.client.make_bucket(bucket)
            except S3Error:
                pass
            self._apply_bucket_sse(bucket)

    def _apply_bucket_sse(self, bucket: str) -> None:
        """桶级默认 SSE-S3；失败只记日志，put 仍会带 SseS3。"""
        try:
            self.client.set_bucket_encryption(
                bucket, SSEConfig(Rule.new_sse_s3_rule())
            )
        except S3Error:
            logger.exception("set bucket sse failed bucket=%s", bucket)

    def upload_file(
        self,
        bucket: str,
        object_name: str,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
    ) -> str:
        """上传文件（SSE-S3），返回 s3://bucket/key。"""
        if isinstance(data, bytes):
            data = BytesIO(data)
        self.client.put_object(
            bucket_name=bucket,
            object_name=object_name,
            data=data,
            length=-1,
            part_size=10 * 1024 * 1024,
            content_type=content_type,
            sse=SseS3(),
        )
        return f"s3://{bucket}/{object_name}"

    def get_presigned_url(self, bucket: str, object_name: str, expires: int = 3600) -> str:
        """生成临时下载 URL。"""
        return self.client.presigned_get_object(
            bucket_name=bucket,
            object_name=object_name,
            expires=timedelta(seconds=expires),
        )

    def delete_file(self, bucket: str, object_name: str) -> None:
        """删除文件。"""
        self.client.remove_object(bucket, object_name)

    def object_exists(self, file_url: str) -> bool:
        """s3://bucket/key 是否还在桶里。"""
        try:
            bucket, key = parse_s3_url(file_url)
        except ValueError:
            return False
        try:
            self.client.stat_object(bucket_name=bucket, object_name=key)
            return True
        except S3Error:
            return False

    def list_objects(self, bucket: str, prefix: str = "") -> list[tuple[str, object]]:
        """列出桶内对象：(object_name, last_modified)。"""
        items: list[tuple[str, object]] = []
        try:
            for obj in self.client.list_objects(bucket, prefix=prefix, recursive=True):
                if obj.object_name:
                    items.append((obj.object_name, obj.last_modified))
        except S3Error:
            logger.exception("list objects failed bucket=%s prefix=%s", bucket, prefix)
        return items

    def download_bytes(self, file_url: str) -> bytes:
        """从 s3://bucket/key 下载对象内容（MinIO 侧解密）。"""
        bucket, key = parse_s3_url(file_url)
        obj = self.client.get_object(bucket_name=bucket, object_name=key)
        try:
            return obj.read()
        finally:
            obj.close()
            obj.release_conn()

    def rewrite_object_with_sse(self, bucket: str, object_name: str) -> str:
        """明文对象同 key 覆盖为 SSE-S3；已加密则 skipped。"""
        stat = self.client.stat_object(bucket_name=bucket, object_name=object_name)
        if object_encrypted_sse_s3(stat):
            return "skipped"
        data = self.download_bytes(f"s3://{bucket}/{object_name}")
        content_type = getattr(stat, "content_type", None) or "application/octet-stream"
        self.upload_file(bucket, object_name, data, content_type=content_type)
        return "rewritten"


def parse_s3_url(s3_url: str) -> tuple[str, str]:
    """s3://bucket/key → (bucket, key)。"""
    if not s3_url.startswith("s3://"):
        raise ValueError(f"invalid s3 url: {s3_url}")
    rest = s3_url[len("s3://") :]
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        raise ValueError(f"invalid s3 url: {s3_url}")
    return bucket, key


storage_service = StorageService()
