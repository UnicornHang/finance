"""MinIO SSE-S3 上传与元数据判断。"""

import importlib.util
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from minio.error import S3Error
from minio.sse import SseS3
from urllib3._collections import HTTPHeaderDict

from app.services.storage_service import object_encrypted_sse_s3, storage_service


def test_object_encrypted_sse_s3_true():
    """元数据带 AES256 视为已加密。"""
    stat = MagicMock()
    stat.metadata = {"X-Amz-Server-Side-Encryption": "AES256"}
    assert object_encrypted_sse_s3(stat) is True


def test_object_encrypted_sse_s3_false_when_empty():
    """无 SSE 头视为明文。"""
    stat = MagicMock()
    stat.metadata = {}
    assert object_encrypted_sse_s3(stat) is False


def test_object_encrypted_sse_s3_true_for_http_header_dict():
    """MinIO stat metadata 为 HTTPHeaderDict 时也应识别 AES256。"""
    stat = MagicMock()
    stat.metadata = HTTPHeaderDict({"X-Amz-Server-Side-Encryption": "AES256"})
    assert object_encrypted_sse_s3(stat) is True


def test_upload_file_passes_sse_s3():
    """put_object 必须带 SseS3。"""
    with patch.object(storage_service.client, "put_object") as put:
        url = storage_service.upload_file(
            bucket="knowledge-base",
            object_name="t/files/by-hash/ab.pdf",
            data=b"%PDF",
            content_type="application/pdf",
        )
    assert url == "s3://knowledge-base/t/files/by-hash/ab.pdf"
    kwargs = put.call_args.kwargs
    assert isinstance(kwargs["sse"], SseS3)
    assert kwargs["bucket_name"] == "knowledge-base"
    assert kwargs["object_name"] == "t/files/by-hash/ab.pdf"
    assert kwargs["content_type"] == "application/pdf"
    assert isinstance(kwargs["data"], BytesIO)


def test_apply_bucket_sse_swallows_s3_error():
    """设桶加密失败只打日志，不抛。"""
    err = S3Error("AccessDenied", "denied", "/", "rid", "hid", MagicMock())
    with patch.object(storage_service.client, "set_bucket_encryption", side_effect=err):
        storage_service._apply_bucket_sse("invoices")


def test_rewrite_object_with_sse_skips_encrypted():
    """已 SSE-S3 的对象不重写。"""
    stat = MagicMock()
    stat.metadata = {"x-amz-server-side-encryption": "AES256"}
    with (
        patch.object(storage_service.client, "stat_object", return_value=stat),
        patch.object(storage_service, "upload_file") as upload,
    ):
        result = storage_service.rewrite_object_with_sse("invoices", "a.pdf")
    assert result == "skipped"
    upload.assert_not_called()


def test_rewrite_object_with_sse_puts_plaintext():
    """明文对象同 key 再 upload（带 SSE）。"""
    stat = MagicMock()
    stat.metadata = {}
    stat.content_type = "application/pdf"
    with (
        patch.object(storage_service.client, "stat_object", return_value=stat),
        patch.object(storage_service, "download_bytes", return_value=b"%PDF"),
        patch.object(storage_service, "upload_file", return_value="s3://invoices/a.pdf") as upload,
    ):
        result = storage_service.rewrite_object_with_sse("invoices", "a.pdf")
    assert result == "rewritten"
    upload.assert_called_once_with(
        "invoices",
        "a.pdf",
        b"%PDF",
        content_type="application/pdf",
    )


def _load_rewrite_script():
    """加载 backend/scripts/rewrite_minio_sse.py。"""
    path = Path(__file__).resolve().parents[1] / "scripts" / "rewrite_minio_sse.py"
    spec = importlib.util.spec_from_file_location("rewrite_minio_sse", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rewrite_bucket_counts(monkeypatch):
    """脚本按 list 结果计数 skipped/rewritten/failed。"""
    mod = _load_rewrite_script()
    monkeypatch.setattr(
        storage_service,
        "list_objects",
        lambda bucket, prefix="": [("plain.pdf", None), ("enc.pdf", None), ("bad.pdf", None)],
    )

    def fake_rewrite(bucket, name):
        if name == "plain.pdf":
            return "rewritten"
        if name == "enc.pdf":
            return "skipped"
        raise RuntimeError("boom")

    monkeypatch.setattr(storage_service, "rewrite_object_with_sse", fake_rewrite)
    skipped, rewritten, failed = mod.rewrite_bucket("invoices")
    assert (skipped, rewritten, failed) == (1, 1, 1)
