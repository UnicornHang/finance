"""权威财税站点：白名单检索 + 受限原文抓取。

搜索引擎用博查/Tavily；本模块只约束「查哪些站、能否打开、如何引用」。
发票查验、公示系统、裁判文书不在此列。
"""

from __future__ import annotations

import ipaddress
import logging
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.web_search_service import WebSearchRuntime, web_search_service

logger = logging.getLogger(__name__)

# 政策检索主信源（含子域，如 kjs.mof.gov.cn、fgk.chinatax.gov.cn）
OFFICIAL_POLICY_DOMAINS: tuple[str, ...] = (
    "mof.gov.cn",
    "chinatax.gov.cn",
    "casc.org.cn",
    "npc.gov.cn",
)

# 可引用但须标明「专业参考平台，非纯官方」
SUPPLEMENTAL_DOMAINS: tuple[str, ...] = ("shui5.cn",)

_ALL_SEARCH_DOMAINS: tuple[str, ...] = OFFICIAL_POLICY_DOMAINS + SUPPLEMENTAL_DOMAINS

_FETCH_MAX_BYTES = 512_000
_DEFAULT_FETCH_CHARS = 4000

_SITE_QUERY = (
    "(site:chinatax.gov.cn OR site:mof.gov.cn OR site:fgk.chinatax.gov.cn "
    "OR site:casc.org.cn OR site:kjs.mof.gov.cn OR site:flk.npc.gov.cn)"
)


class _HTMLTextExtractor(HTMLParser):
    """去掉 script/style，抽出可读正文。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1
        elif tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = data.strip()
        if text:
            self.parts.append(text)


def _host_matches(host: str, domain: str) -> bool:
    """host 是否为 domain 或其子域。"""
    h = host.lower().rstrip(".")
    d = domain.lower().rstrip(".")
    return h == d or h.endswith("." + d)


def _is_ip_host(host: str) -> bool:
    """主机名是否为 IP（禁止用 IP 绕过白名单）。"""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def classify_official_host(host: str) -> str | None:
    """返回 official / supplemental；不在名单则为 None。"""
    h = (host or "").lower().rstrip(".")
    if not h or _is_ip_host(h):
        return None
    for domain in OFFICIAL_POLICY_DOMAINS:
        if _host_matches(h, domain):
            return "official"
    for domain in SUPPLEMENTAL_DOMAINS:
        if _host_matches(h, domain):
            return "supplemental"
    return None


def is_allowed_official_url(url: str, *, allow_supplemental: bool = True) -> bool:
    """仅允许 https + 白名单域名，拒绝用户信息、非 443 端口、IP 主机。"""
    raw = (url or "").strip()
    try:
        parsed = urlparse(raw)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    if parsed.username or parsed.password:
        return False
    if parsed.port not in (None, 443):
        return False
    host = (parsed.hostname or "").lower()
    kind = classify_official_host(host)
    if kind == "official":
        return True
    if kind == "supplemental" and allow_supplemental:
        return True
    return False


def extract_html_text(html: str, *, max_chars: int) -> str:
    """HTML → 纯文本，截断到 max_chars。"""
    parser = _HTMLTextExtractor()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html or "")
        return re.sub(r"\s+", " ", text).strip()[:max_chars]
    text = "".join(parser.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_chars]


def boost_official_policy_query(question: str) -> str:
    """检索词加上官方站点限定，避免全网噪声。"""
    q = (question or "").strip()
    if not q:
        return q
    return f"{q} 政策 法规 {_SITE_QUERY}"


def format_official_policy_context(result: dict[str, Any]) -> str:
    """把白名单检索 + 原文抽取格式化为提示词资料。"""
    if not result.get("ok"):
        err = result.get("error") or "检索不可用"
        return f"（权威站点检索失败：{err}。不得编造最新税率、优惠幅度或文件文号。）"
    hits = result.get("hits") or []
    pages = result.get("pages") or []
    if not hits and not pages:
        return "（未在财政部、税务总局、法规库等权威网站检索到相关公开资料。请明确告知用户暂无可靠来源，禁止编造。）"
    parts: list[str] = []
    for i, h in enumerate(hits, start=1):
        title = h.get("title") or "未命名"
        url = h.get("url") or ""
        published = h.get("published_at") or ""
        snippet = (h.get("snippet") or "").strip()
        source_kind = h.get("source_kind") or "official"
        label = "专业参考平台（非纯官方）" if source_kind == "supplemental" else "权威官网"
        meta = f"[{i}] （{label}）{title}"
        if published:
            meta += f"（时间:{published}）"
        if url:
            meta += f"\n链接: {url}"
        parts.append(f"{meta}\n{snippet}")
    for j, page in enumerate(pages, start=1):
        url = page.get("url") or ""
        title = page.get("title") or url
        body = (page.get("text") or "").strip()
        if not body:
            continue
        parts.append(f"【原文{j}】{title}\n链接: {url}\n{body}")
    return "\n\n".join(parts)


class OfficialPolicyService:
    """search_official_policy + fetch_official_page。"""

    async def search_and_fetch(
        self,
        question: str,
        *,
        runtime: WebSearchRuntime | None = None,
    ) -> dict[str, Any]:
        """白名单检索，并对前几条官方结果抓取正文。"""
        rt = runtime or WebSearchRuntime.from_settings()
        query = boost_official_policy_query(question)
        search = await web_search_service.search(
            query,
            runtime=rt,
            max_results=rt.max_results,
            include_domains=list(_ALL_SEARCH_DOMAINS),
        )
        raw_hits = search.get("hits") or []
        hits: list[dict[str, str]] = []
        for item in raw_hits:
            url = item.get("url") or ""
            if not is_allowed_official_url(url):
                logger.info("drop off-whitelist search hit url=%s", url[:120])
                continue
            host = (urlparse(url).hostname or "")
            kind = classify_official_host(host) or "official"
            hits.append({**item, "source_kind": kind})

        pages: list[dict[str, str]] = []
        fetch_n = rt.fetch_pages
        if fetch_n > 0 and hits:
            official_first = [h for h in hits if h.get("source_kind") == "official"]
            to_fetch = official_first[:fetch_n] or hits[:fetch_n]
            for h in to_fetch:
                page = await self.fetch_official_page(h.get("url") or "", runtime=rt)
                if page.get("ok") and page.get("text"):
                    pages.append(
                        {
                            "url": str(page.get("final_url") or h.get("url") or ""),
                            "title": str(page.get("title") or h.get("title") or ""),
                            "text": str(page.get("text") or ""),
                        }
                    )

        ok = bool(search.get("ok"))
        error = search.get("error")
        if ok and not hits:
            error = error or "检索结果均不在权威站点白名单内"
        return {
            "ok": ok and bool(hits or pages),
            "provider": search.get("provider"),
            "query": query,
            "hits": hits,
            "pages": pages,
            "error": None if (ok and (hits or pages)) else error,
        }

    async def fetch_official_page(
        self,
        url: str,
        *,
        runtime: WebSearchRuntime | None = None,
    ) -> dict[str, Any]:
        """只抓取白名单 https 页面正文。"""
        rt = runtime or WebSearchRuntime.from_settings()
        if not is_allowed_official_url(url):
            return {"ok": False, "url": url, "error": "URL 不在权威站点白名单"}
        max_chars = rt.fetch_max_chars or _DEFAULT_FETCH_CHARS
        timeout = rt.timeout
        headers = {
            "User-Agent": "FinanceAI-OfficialPolicyBot/1.0",
            "Accept": "text/html,application/xhtml+xml",
        }
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                max_redirects=5,
            ) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("fetch official page failed url=%s err=%s", url[:120], exc)
            return {"ok": False, "url": url, "error": str(exc)}

        final_url = str(resp.url)
        if not is_allowed_official_url(final_url):
            return {
                "ok": False,
                "url": url,
                "error": f"重定向后离开白名单: {final_url[:120]}",
            }
        content_type = (resp.headers.get("content-type") or "").lower()
        if "html" not in content_type and "text" not in content_type:
            return {"ok": False, "url": final_url, "error": f"不支持的类型: {content_type}"}
        raw = resp.content[:_FETCH_MAX_BYTES]
        html = raw.decode(resp.encoding or "utf-8", errors="replace")
        title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""
        text = extract_html_text(html, max_chars=max_chars)
        if not text:
            return {"ok": False, "url": final_url, "error": "页面无可用正文"}
        return {
            "ok": True,
            "url": url,
            "final_url": final_url,
            "title": title,
            "text": text,
            "error": None,
        }


official_policy_service = OfficialPolicyService()
