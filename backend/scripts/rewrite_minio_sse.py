"""将 MinIO 业务桶中的明文对象同 key 重写为 SSE-S3。

用法（在 backend 目录）：
    python scripts/rewrite_minio_sse.py
    python scripts/rewrite_minio_sse.py --bucket knowledge-base
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.storage_service import storage_service  # noqa: E402

logger = logging.getLogger("rewrite_minio_sse")


def rewrite_bucket(bucket: str) -> tuple[int, int, int]:
    """回写一个桶。返回 (skipped, rewritten, failed)。"""
    skipped = rewritten = failed = 0
    for object_name, _modified in storage_service.list_objects(bucket):
        try:
            result = storage_service.rewrite_object_with_sse(bucket, object_name)
            if result == "skipped":
                skipped += 1
            else:
                rewritten += 1
        except Exception:
            failed += 1
            logger.exception("rewrite failed bucket=%s key=%s", bucket, object_name)
    return skipped, rewritten, failed


def main(argv: list[str] | None = None) -> int:
    """解析 --bucket 并回写。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Rewrite MinIO objects with SSE-S3")
    parser.add_argument(
        "--bucket",
        default=None,
        help="只处理指定桶；默认 invoices + contracts + knowledge-base",
    )
    args = parser.parse_args(argv)
    buckets = (
        [args.bucket] if args.bucket else storage_service._business_buckets()
    )
    total_s = total_r = total_f = 0
    for bucket in buckets:
        skipped, rewritten, failed = rewrite_bucket(bucket)
        logger.info(
            "bucket=%s skipped=%s rewritten=%s failed=%s",
            bucket,
            skipped,
            rewritten,
            failed,
        )
        total_s += skipped
        total_r += rewritten
        total_f += failed
    logger.info("done skipped=%s rewritten=%s failed=%s", total_s, total_r, total_f)
    return 1 if total_f else 0


if __name__ == "__main__":
    raise SystemExit(main())
