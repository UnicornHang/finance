"""OCR 服务 - 抽象 + 多 Provider 实现 + 工厂。

Phase A 实现：
- TencentOCRProvider: 调用腾讯云 MixedInvoiceOCR（增值税发票识别）
- get_ocr_service: 根据 settings 决定降级到 Mock 还是真实 SDK
"""

import base64
import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class InvoiceOCRResult:
    """OCR 识别结果（与 Invoice 模型字段一一对应）。"""

    invoice_title: str | None = None
    company: str | None = None
    tax_id: str | None = None
    invoice_code: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    amount_excl_tax: float | None = None
    tax_amount: float | None = None
    amount_incl_tax: float | None = None
    invoice_type: str | None = None  # special / general / electronic
    seller: str | None = None
    buyer: str | None = None
    confidence: dict[str, float] | None = None


class OCRProvider(ABC):
    """OCR 提供商抽象。"""

    @abstractmethod
    async def recognize_invoice(self, file_bytes: bytes) -> InvoiceOCRResult:
        """识别发票，返回结构化字段。"""


# ================ Mock（开发/无密钥降级） ================

class MockOCRProvider(OCRProvider):
    """本地 Mock OCR：基于 file_bytes 哈希生成稳定伪数据，便于开发与测试。"""

    async def recognize_invoice(self, file_bytes: bytes) -> InvoiceOCRResult:
        h = hashlib.sha256(file_bytes).hexdigest()[:8]
        seed_num = int(h, 16) % 10**8
        return InvoiceOCRResult(
            invoice_title=f"模拟发票 {h.upper()}",
            company="模拟开票方有限公司",
            tax_id="91110000" + h.upper().ljust(8, "X") + "X",
            invoice_code=f"MOCK{h[:6].upper()}",
            invoice_number=f"{seed_num:08d}",
            invoice_date=date.today(),
            amount_excl_tax=1000.00,
            tax_amount=130.00,
            amount_incl_tax=1130.00,
            invoice_type="electronic",
            seller="模拟销售方科技有限公司",
            buyer="模拟购买方股份有限公司",
            confidence={
                "invoice_number": 0.95,
                "amount": 0.99,
                "invoice_date": 0.93,
                "tax_id": 0.88,
            },
        )


# ================ 腾讯云 OCR ================

class TencentOCRProvider(OCRProvider):
    """腾讯云 OCR：调用 MixedInvoiceOCR API。

    文档：https://cloud.tencent.com/document/api/866/49500
    需要：TENCENT_OCR_SECRET_ID + TENCENT_OCR_SECRET_KEY + Region
    """

    async def recognize_invoice(self, file_bytes: bytes) -> InvoiceOCRResult:
        if not settings.tencent_ocr_secret_id or not settings.tencent_ocr_secret_key:
            # 双保险：factory 已降级，这里再兜底
            logger.warning("Tencent OCR credentials missing, falling back to Mock")
            return await MockOCRProvider().recognize_invoice(file_bytes)

        try:
            # 延迟 import：SDK 体积大，按需加载
            from tencentcloud.common import credential
            from tencentcloud.ocr.v20181119 import models, ocr_client

            cred = credential.Credential(
                settings.tencent_ocr_secret_id,
                settings.tencent_ocr_secret_key,
            )
            client = ocr_client.OcrClient(cred, settings.tencent_ocr_region)

            req = models.MixedInvoiceOCRRequest()
            req.ImageBase64 = base64.b64encode(file_bytes).decode("utf-8")

            logger.info("Tencent OCR request: %d bytes, region=%s", len(file_bytes), settings.tencent_ocr_region)
            resp = client.MixedInvoiceOCR(req)

            return _map_tencent_response(resp)

        except Exception as exc:
            logger.exception("Tencent OCR failed: %s", exc)
            raise


def _map_tencent_response(resp) -> InvoiceOCRResult:
    """把腾讯云 MixedInvoiceOCR 响应映射成 InvoiceOCRResult。

    腾讯云返回 MixedInvoiceItems 数组，每项含 VatInvoiceInfo / ElectronicInvoiceInfo 等子结构。
    这里只取第一张增值税发票的字段作为代表（多数场景是单张）。
    """
    items = getattr(resp, "MixedInvoiceItems", []) or []
    if not items:
        logger.warning("Tencent OCR returned no MixedInvoiceItems")
        return InvoiceOCRResult()

    item = items[0]
    # 不同发票类型字段位置不同：优先 VatInvoiceInfo（增值税发票）
    vat = getattr(item, "VatInvoiceInfo", None)
    if vat is None:
        # 电子发票 fallback
        vat = getattr(item, "ElectronicInvoiceInfo", None)

    if vat is None:
        # 最后兜底：直接用 item 自身（保守取字段）
        vat = item

    # 字段提取（容错：可能为 None 或 str/Decimal）
    def _s(obj, *names):
        for n in names:
            v = getattr(obj, n, None)
            if v:
                return v
        return None

    def _f(obj, *names):
        v = _s(obj, *names)
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    def _date(obj, *names):
        v = _s(obj, *names)
        if v is None:
            return None
        try:
            # 腾讯云常见格式 "2024-01-15" 或 "20240115"
            if isinstance(v, datetime):
                return v.date()
            if isinstance(v, date):
                return v
            s = str(v)
            if len(s) == 8 and s.isdigit():
                return datetime.strptime(s, "%Y%m%d").date()
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

    confidence = {}
    if hasattr(item, "Confidence") and item.Confidence is not None:
        try:
            confidence = dict(item.Confidence) if hasattr(item.Confidence, "items") else {}
        except Exception:
            confidence = {}

    return InvoiceOCRResult(
        invoice_title=_s(vat, "Title", "InvoiceTitle"),
        company=_s(vat, "Seller", "SellerName", "CompanyName"),
        tax_id=_s(vat, "SellerTaxID", "TaxId"),
        invoice_code=_s(vat, "Code", "InvoiceCode"),
        invoice_number=_s(vat, "Number", "InvoiceNumber"),
        invoice_date=_date(vat, "Date", "InvoiceDate", "IssueDate"),
        amount_excl_tax=_f(vat, "AmountWithoutTax", "Price", "PretaxAmount"),
        tax_amount=_f(vat, "TaxAmount", "Tax"),
        amount_incl_tax=_f(vat, "AmountWithTax", "Total", "Amount"),
        invoice_type="special" if getattr(item, "VatInvoiceInfo", None) else "electronic",
        seller=_s(vat, "Seller", "SellerName"),
        buyer=_s(vat, "Buyer", "BuyerName"),
        confidence=confidence or None,
    )


# ================ 工厂 ================

def get_ocr_service() -> OCRProvider:
    """根据 settings 返回 OCR 实例；密钥缺失时降级 Mock。"""
    if not settings.tencent_ocr_secret_id or not settings.tencent_ocr_secret_key:
        logger.info("OCR: tencent credentials missing → using MockOCRProvider")
        return MockOCRProvider()

    if settings.ocr_provider == "tencent":
        return TencentOCRProvider()

    if settings.ocr_provider == "aliyun":
        # TODO: 阿里云 OCR（不在 Phase A 范围）
        logger.warning("Aliyun OCR not implemented in Phase A, using Mock")
        return MockOCRProvider()

    if settings.ocr_provider == "paddle":
        # TODO: PaddleOCR 本地（不在 Phase A 范围）
        logger.warning("PaddleOCR not implemented in Phase A, using Mock")
        return MockOCRProvider()

    raise ValueError(f"Unknown OCR provider: {settings.ocr_provider}")