"""发票 Vision 识别（方案 B 验证）：多模态模型主路径，失败再回落 OCR。

返回 (InvoiceOCRResult, source)，source ∈ {"vision", "ocr"}。
"""

from __future__ import annotations

import base64
import json
import logging
import re
from datetime import date, datetime
from typing import TYPE_CHECKING

from app.services.ocr_service import InvoiceOCRResult, get_ocr_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 可走 Vision 的图片 MIME（PDF 验证期直接回落 OCR，避免模型不支持）
_IMAGE_MIME = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}

_VISION_PROMPT = """你是中国增值税发票识别专家。请从图片中提取字段，只返回一个 JSON 对象，不要 Markdown，不要解释。

字段（缺省用 null）：
{
  "invoice_title": "发票抬头或标题",
  "company": "开票公司/销售方",
  "tax_id": "纳税人识别号（销售方）",
  "invoice_code": "发票代码",
  "invoice_number": "发票号码",
  "invoice_date": "开票日期 YYYY-MM-DD",
  "amount_excl_tax": 不含税金额数字,
  "tax_amount": 税额数字,
  "amount_incl_tax": 价税合计数字,
  "invoice_type": "special|general|electronic 之一",
  "seller": "销售方名称",
  "buyer": "购买方名称"
}

要求：金额必须是数字；日期必须是 YYYY-MM-DD；看不清的字段填 null。
"""


def _guess_mime(file_bytes: bytes, content_type: str | None, filename: str | None) -> str:
    """推断 MIME：优先 content_type，其次魔数，再次文件名后缀。"""
    if content_type and content_type.split(";")[0].strip().lower() in _IMAGE_MIME:
        return content_type.split(";")[0].strip().lower()
    if content_type and content_type.startswith("image/"):
        return content_type.split(";")[0].strip().lower()

    if file_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        return "image/webp"
    if file_bytes[:4] == b"%PDF":
        return "application/pdf"

    name = (filename or "").lower()
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".pdf"):
        return "application/pdf"
    return content_type or "application/octet-stream"


def _parse_json_object(text: str) -> dict:
    """从模型输出中抽出 JSON 对象。"""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("模型返回空内容")

    # 去掉 ```json ... ``` 围栏
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()

    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        obj = json.loads(raw[start : end + 1])
        if isinstance(obj, dict):
            return obj
    raise ValueError(f"无法解析模型 JSON：{raw[:200]}")


def _to_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    try:
        if len(s) == 8 and s.isdigit():
            return datetime.strptime(s, "%Y%m%d").date()
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _to_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _dict_to_result(data: dict) -> InvoiceOCRResult:
    """把 Vision JSON 映射为 InvoiceOCRResult。"""
    inv_type = data.get("invoice_type")
    if inv_type not in ("special", "general", "electronic", None):
        inv_type = "electronic"

    return InvoiceOCRResult(
        invoice_title=data.get("invoice_title") or None,
        company=data.get("company") or None,
        tax_id=data.get("tax_id") or None,
        invoice_code=data.get("invoice_code") or None,
        invoice_number=data.get("invoice_number") or None,
        invoice_date=_to_date(data.get("invoice_date")),
        amount_excl_tax=_to_float(data.get("amount_excl_tax")),
        tax_amount=_to_float(data.get("tax_amount")),
        amount_incl_tax=_to_float(data.get("amount_incl_tax")),
        invoice_type=inv_type,
        seller=data.get("seller") or None,
        buyer=data.get("buyer") or None,
        confidence={"vision": 1.0},
    )


def _is_usable(result: InvoiceOCRResult) -> bool:
    """至少要有号码或价税合计之一，才算识别成功。"""
    return bool(result.invoice_number) or result.amount_incl_tax is not None


class InvoiceVisionService:
    """方案 B：Vision 主识别，OCR 兜底。"""

    async def recognize(
        self,
        file_bytes: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
        db: "AsyncSession | None" = None,
        tenant_id: str | None = None,
    ) -> tuple[InvoiceOCRResult, str]:
        """识别发票。

        Returns:
            (result, source) — source 为 "vision" 或 "ocr"
        """
        mime = _guess_mime(file_bytes, content_type, filename)

        # 非图片：验证期直接 OCR（避免 PDF 多模态兼容问题）
        if mime not in _IMAGE_MIME:
            logger.info("invoice vision skip mime=%s → OCR fallback", mime)
            result = await get_ocr_service().recognize_invoice(file_bytes)
            return result, "ocr"

        # 1) Vision 主路径
        try:
            result = await self._vision_recognize(
                file_bytes, mime, db=db, tenant_id=tenant_id
            )
            if _is_usable(result):
                logger.info(
                    "invoice vision ok: number=%s amount=%s",
                    result.invoice_number,
                    result.amount_incl_tax,
                )
                return result, "vision"
            logger.warning("invoice vision returned unusable fields → OCR fallback")
        except Exception as exc:
            logger.warning("invoice vision failed → OCR fallback: %s", exc, exc_info=True)

        # 2) OCR 兜底
        result = await get_ocr_service().recognize_invoice(file_bytes)
        return result, "ocr"

    async def _vision_recognize(
        self,
        file_bytes: bytes,
        mime: str,
        *,
        db: "AsyncSession | None",
        tenant_id: str | None,
    ) -> InvoiceOCRResult:
        """调用 ocr_post 场景的多模态模型抽取 JSON。"""
        from app.services.llm_service import llm_service

        b64 = base64.b64encode(file_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]

        text = await llm_service.invoke(
            messages,
            scene="ocr_post",
            db=db,
            tenant_id=tenant_id,
            temperature=0.1,
            max_tokens=1500,
        )
        data = _parse_json_object(text)
        return _dict_to_result(data)


invoice_vision_service = InvoiceVisionService()
