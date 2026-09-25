"""发票识别：全程由通用多模态大模型完成，不调用 OCR 引擎。

图片走 image_url，PDF / 其他文件走 file 内容块，同一模型抽取结构化字段。
返回 (InvoiceOCRResult, source)，source 固定为 "llm"。
"""

from __future__ import annotations

import base64
import json
import logging
import re
import zipfile
from datetime import date, datetime
from io import BytesIO
from typing import TYPE_CHECKING
from uuid import UUID
from xml.etree import ElementTree

from app.services.ocr_service import InvoiceOCRResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 按图片块发送的 MIME（其余文件按 file 块交给同一模型）
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


def _docx_text(file_bytes: bytes) -> str:
    """从 docx 的 word/document.xml 抽出纯文本。"""
    try:
        with zipfile.ZipFile(BytesIO(file_bytes)) as zf:
            xml = zf.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError):
        return ""
    root = ElementTree.fromstring(xml)
    parts = [node.text for node in root.iter() if node.text and node.text.strip()]
    return "\n".join(parts)


def _pdf_text(file_bytes: bytes) -> str:
    """尽量抽出 PDF 里的可见文字。扫描件通常抽不到，需要改传图片。"""
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(file_bytes))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        raw = file_bytes.decode("latin1", errors="ignore")
        chunks = re.findall(r"\((?:\\.|[^\\)]){2,}\)", raw)
        texts = []
        for chunk in chunks[:400]:
            inner = chunk[1:-1].replace("\\n", "\n").replace("\\r", "")
            if any("\u4e00" <= ch <= "\u9fff" for ch in inner) or any(ch.isdigit() for ch in inner):
                texts.append(inner)
        return "\n".join(texts)


def _extract_file_text(file_bytes: bytes, mime: str, filename: str | None) -> str:
    """非图片文件转成文本，交给同一个大模型抽取字段。"""
    name = (filename or "").lower()
    if mime == "application/pdf" or name.endswith(".pdf"):
        return _pdf_text(file_bytes)
    if "wordprocessingml" in mime or name.endswith(".docx"):
        return _docx_text(file_bytes)
    if name.endswith(".doc"):
        return ""
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return ""


async def _resolve_recognition_config(db, tenant_id: str | None) -> dict | None:
    """优先单据识别场景；没密钥时改用已配置密钥的日常对话模型。"""
    if db is None or not tenant_id:
        return None
    from app.services.llm_config_service import llm_config_service

    tid = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
    for scene in ("ocr_post", "chitchat"):
        cfg = await llm_config_service.resolve(db, tid, scene)
        if cfg and (cfg.get("api_key") or "").strip() and _model_matches_provider(cfg):
            logger.info(
                "invoice recognize model scene=%s provider=%s model=%s",
                scene,
                cfg.get("provider"),
                cfg.get("model"),
            )
            return cfg
    return None


def _model_matches_provider(cfg: dict) -> bool:
    """DashScope 上不能用 gpt-4o 这类非通义模型名，否则请求失败后会得到假数据。"""
    provider = (cfg.get("provider") or "").lower()
    model = (cfg.get("model") or "").lower()
    if provider == "dashscope":
        return model.startswith("qwen")
    return bool(model)


def _media_content(
    file_bytes: bytes, mime: str, filename: str | None, instruction: str
) -> list[dict]:
    """图片附 image_url，其他文件附抽出的文本。"""
    content: list[dict] = [{"type": "text", "text": instruction}]
    if mime in _IMAGE_MIME or mime.startswith("image/"):
        b64 = base64.b64encode(file_bytes).decode("ascii")
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
        )
        return content
    extracted = _extract_file_text(file_bytes, mime, filename)
    content.append(
        {
            "type": "text",
            "text": f"文件《{filename or '附件'}》文本：\n{(extracted or '（未能抽出文字）')[:12000]}",
        }
    )
    return content


def _is_usable(result: InvoiceOCRResult) -> bool:
    """至少要有号码或价税合计之一，才算识别成功。"""
    return bool(result.invoice_number) or result.amount_incl_tax is not None


class InvoiceVisionService:
    """通用大模型识别图片与文件，不回落 OCR。"""

    async def recognize(
        self,
        file_bytes: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
        db: "AsyncSession | None" = None,
        tenant_id: str | None = None,
    ) -> tuple[InvoiceOCRResult, str]:
        """识别发票。图片与 PDF/文件都交给同一多模态模型。

        Returns:
            (result, source) — source 固定为 "llm"
        """
        mime = _guess_mime(file_bytes, content_type, filename)
        result = await self._llm_recognize(
            file_bytes,
            mime,
            filename=filename,
            db=db,
            tenant_id=tenant_id,
        )
        if not _is_usable(result):
            raise ValueError("大模型未识别出发票号码或价税合计，请换一张更清晰的图片或文件后重试")
        logger.info(
            "invoice llm ok mime=%s number=%s amount=%s",
            mime,
            result.invoice_number,
            result.amount_incl_tax,
        )
        return result, "llm"

    async def _llm_recognize(
        self,
        file_bytes: bytes,
        mime: str,
        *,
        filename: str | None,
        db: "AsyncSession | None",
        tenant_id: str | None,
    ) -> InvoiceOCRResult:
        """调用已配置且有密钥的多模态模型抽取 JSON。

        单据识别场景没配密钥时，改用日常对话里已配置的通用模型（如 qwen3.7-flash）。
        图片走 image_url；PDF/Word 先抽出文本再交给同一模型，避免空密钥请求打出同一段失败话术。
        """
        from app.services.llm_service import llm_service

        cfg = await _resolve_recognition_config(db, tenant_id)
        if cfg is None:
            raise ValueError(
                "没有可用的大模型密钥。请在系统设置里为「日常对话」或「单据识别」填写 API Key"
            )

        content: list[dict] = [{"type": "text", "text": _VISION_PROMPT}]
        if mime in _IMAGE_MIME or mime.startswith("image/"):
            b64 = base64.b64encode(file_bytes).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                }
            )
        else:
            extracted = _extract_file_text(file_bytes, mime, filename)
            if not extracted.strip():
                raise ValueError(
                    "当前模型只能直接看图片。PDF/Word 里没有可提取的文字，请改上传发票图片"
                )
            content.append(
                {
                    "type": "text",
                    "text": f"以下是文件《{filename or '附件'}》的文本，请按上面的 JSON 字段抽取：\n{extracted[:12000]}",
                }
            )

        messages = [{"role": "user", "content": content}]
        text = await llm_service.complete_with_config(
            messages,
            cfg,
            temperature=0.1,
            max_tokens=1500,
            apply_scene_prompt=False,
        )
        if not text.strip():
            raise ValueError("大模型返回空内容，请确认模型支持看图（如 qwen3.7-flash）")
        data = _parse_json_object(text)
        return _dict_to_result(data)

    async def classify(
        self,
        file_bytes: bytes,
        *,
        content_type: str | None,
        filename: str | None,
        user_message: str,
        db: "AsyncSession | None",
        tenant_id: str | None,
    ) -> str:
        """先看附件和用户原话，判断该交给哪个业务。返回 invoice / contract / chat。"""
        from app.services.llm_service import llm_service

        cfg = await _resolve_recognition_config(db, tenant_id)
        if cfg is None:
            raise ValueError("没有可用的大模型密钥，无法判断文件类型")

        mime = _guess_mime(file_bytes, content_type, filename)
        instruction = (
            "你是调度员。结合用户原话和附件内容，判断应交给哪个业务。"
            "只返回 JSON，不要解释："
            '{"intent":"invoice"|"contract"|"chat"}。'
            "invoice=发票、收据、账单、报销凭证；"
            "contract=合同、协议；"
            "chat=其他文件或普通提问。"
            f"\n用户原话：{user_message or '（未填写）'}"
        )
        content = _media_content(file_bytes, mime, filename, instruction)
        text = await llm_service.complete_with_config(
            [{"role": "user", "content": content}],
            cfg,
            temperature=0.0,
            max_tokens=200,
            apply_scene_prompt=False,
        )
        data = _parse_json_object(text)
        intent = str(data.get("intent") or "chat").strip().lower()
        if intent not in {"invoice", "contract", "chat"}:
            return "chat"
        logger.info("upload classified as %s file=%s", intent, filename)
        return intent


invoice_vision_service = InvoiceVisionService()
