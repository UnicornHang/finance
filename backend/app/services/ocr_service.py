"""OCR 服务 - 抽象 + 多 Provider 实现。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class InvoiceOCRResult:
    """OCR 识别结果。"""

    invoice_title: str | None = None
    company: str | None = None
    tax_id: str | None = None
    invoice_code: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    amount_excl_tax: float | None = None
    tax_amount: float | None = None
    amount_incl_tax: float | None = None
    invoice_type: str | None = None
    seller: str | None = None
    buyer: str | None = None
    confidence: dict[str, float] | None = None


class OCRProvider(ABC):
    """OCR 提供商抽象。"""

    @abstractmethod
    async def recognize_invoice(self, file_bytes: bytes) -> InvoiceOCRResult:
        """识别发票。"""


class TencentOCRProvider(OCRProvider):
    """腾讯云 OCR（占位实现，需接入官方 SDK）。"""

    async def recognize_invoice(self, file_bytes: bytes) -> InvoiceOCRResult:
        # TODO: 接入 tencentcloud-sdk-python
        # from tencentcloud.ocr.v20181119 import ocr_client, models
        # ...
        raise NotImplementedError("腾讯云 OCR 待接入")


class PaddleOCRProvider(OCRProvider):
    """本地 PaddleOCR（占位实现）。"""

    async def recognize_invoice(self, file_bytes: bytes) -> InvoiceOCRResult:
        raise NotImplementedError("PaddleOCR 本地部署待接入")


# 工厂
def get_ocr_service() -> OCRProvider:
    """根据配置返回 OCR 实例。"""
    from app.config import settings

    if settings.ocr_provider == "tencent":
        return TencentOCRProvider()
    elif settings.ocr_provider == "paddle":
        return PaddleOCRProvider()
    else:
        raise ValueError(f"Unknown OCR provider: {settings.ocr_provider}")