"""OCR 服务 - 抽象 + 多 Provider 实现 + 工厂。

Phase A 实现：
- TencentOCRProvider: 调用腾讯云通用票据识别 RecognizeGeneralInvoice
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


# 通用票据识别 SingleInvoiceInfos 上优先采用的增值税票种（其余票种作兜底）。
_VAT_SUBTYPES: tuple[str, ...] = (
    "VatSpecialInvoice",
    "VatElectronicSpecialInvoice",
    "VatElectronicSpecialInvoiceFull",
    "VatCommonInvoice",
    "VatElectronicCommonInvoice",
    "VatElectronicInvoiceFull",
    "VatElectronicInvoiceBlockchain",
    "VatElectronicInvoiceToll",
    "VatInvoiceRoll",
)

_SPECIAL_SUBTYPES = frozenset({
    "VatSpecialInvoice",
    "VatElectronicSpecialInvoice",
    "VatElectronicSpecialInvoiceFull",
})
_GENERAL_SUBTYPES = frozenset({
    "VatCommonInvoice",
    "VatElectronicCommonInvoice",
    "VatInvoiceRoll",
    "VatElectronicInvoiceToll",
    "MachinePrintedInvoice",
})


class TencentOCRProvider(OCRProvider):
    """腾讯云通用票据识别 RecognizeGeneralInvoice。

    文档：https://cloud.tencent.com/document/product/866/90802
    需要：TENCENT_OCR_SECRET_ID + TENCENT_OCR_SECRET_KEY + Region
    """

    async def recognize_invoice(self, file_bytes: bytes) -> InvoiceOCRResult:
        """把发票图片或 PDF 交给腾讯云通用票据识别，并映射成标准字段。"""
        if not settings.tencent_ocr_secret_id or not settings.tencent_ocr_secret_key:
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

            req = models.RecognizeGeneralInvoiceRequest()
            req.ImageBase64 = base64.b64encode(file_bytes).decode("utf-8")
            # PDF 发票同样走该接口；多页时取全部页
            req.EnablePdf = True
            req.EnableMultiplePage = True

            logger.info(
                "Tencent RecognizeGeneralInvoice: %d bytes, region=%s",
                len(file_bytes),
                settings.tencent_ocr_region,
            )
            resp = client.RecognizeGeneralInvoice(req)
            return _map_tencent_response(resp)

        except Exception as exc:
            logger.exception("Tencent OCR failed: %s", exc)
            raise


def _map_tencent_response(resp) -> InvoiceOCRResult:
    """把 RecognizeGeneralInvoice 的 MixedInvoiceItems 映射成 InvoiceOCRResult。"""
    items = getattr(resp, "MixedInvoiceItems", None) or []
    if not items:
        logger.warning("Tencent OCR returned no MixedInvoiceItems")
        return InvoiceOCRResult()

    subtype, info, type_desc = _pick_invoice_payload(items)
    if info is None:
        logger.warning("Tencent OCR item has empty SingleInvoiceInfos")
        return InvoiceOCRResult(invoice_title=type_desc)

    return InvoiceOCRResult(
        invoice_title=_text(info, "Title") or type_desc,
        company=_text(info, "Seller", "SellerName"),
        tax_id=_text(info, "SellerTaxID"),
        invoice_code=_text(info, "Code"),
        invoice_number=_text(info, "Number", "ElectronicFullNumber", "ElectronicTicketNum"),
        invoice_date=_parse_date(_text(info, "Date", "DateGetOn")),
        amount_excl_tax=_amount(info, "PretaxAmount", "Fare"),
        tax_amount=_amount(info, "Tax"),
        amount_incl_tax=_amount(info, "Total"),
        invoice_type=_invoice_type(subtype),
        seller=_text(info, "Seller", "SellerName"),
        buyer=_text(info, "Buyer", "BuyerName"),
    )


def _pick_invoice_payload(items) -> tuple[str | None, object | None, str | None]:
    """多张票据时优先取增值税发票，否则取第一张有结构化字段的票据。"""
    candidates: list[tuple[str | None, object, str | None]] = []
    for item in items:
        infos = getattr(item, "SingleInvoiceInfos", None)
        if infos is None:
            continue
        type_desc = getattr(item, "TypeDescription", None) or getattr(item, "SubTypeDescription", None)
        for name in _VAT_SUBTYPES:
            payload = getattr(infos, name, None)
            if payload is not None:
                return name, payload, type_desc
        for name in dir(infos):
            if not name[:1].isupper() or name in {"RequestId"}:
                continue
            payload = getattr(infos, name, None)
            if payload is not None:
                candidates.append((name, payload, type_desc))
                break
    if candidates:
        return candidates[0]
    return None, None, None


def _invoice_type(subtype: str | None) -> str:
    """把腾讯云票种子类型收成 special / general / electronic。"""
    if subtype in _SPECIAL_SUBTYPES:
        return "special"
    if subtype in _GENERAL_SUBTYPES:
        return "general"
    return "electronic"


def _text(obj, *names: str) -> str | None:
    """按候选字段名取第一个非空字符串。"""
    for name in names:
        value = getattr(obj, name, None)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _amount(obj, *names: str) -> float | None:
    """解析金额字符串，去掉货币符号和千分位。"""
    raw = _text(obj, *names)
    if raw is None:
        return None
    cleaned = raw.replace(",", "").replace("，", "").replace("¥", "").replace("￥", "").strip()
    try:
        return float(Decimal(cleaned))
    except Exception:
        return None


def _parse_date(raw: str | None) -> date | None:
    """解析腾讯云日期：YYYY-MM-DD、YYYYMMDD、YYYY年MM月DD日。"""
    if not raw:
        return None
    text = raw.strip().replace("年", "-").replace("月", "-").replace("日", "")
    for fmt, width in (("%Y-%m-%d", 10), ("%Y%m%d", 8)):
        try:
            return datetime.strptime(text[:width], fmt).date()
        except ValueError:
            continue
    return None


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