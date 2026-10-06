"""权威财税站点：白名单检索 + 受限原文抓取。

搜索引擎用博查/Tavily；本模块只约束「查哪些站、能否打开、如何引用」。
发票查验、公示系统、裁判文书不在此列。
"""

from __future__ import annotations

import ipaddress
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.web_search_service import WebSearchRuntime, web_search_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProvincialOfficialSource:
    """一个省级行政区的检索别名与政府门户根域名。"""

    name: str
    aliases: tuple[str, ...]
    domains: tuple[str, ...]


# 大陆 31 个省级行政区政府门户根域名；财政厅、统计局等子域自动继承白名单。
PROVINCIAL_OFFICIAL_SOURCES: tuple[ProvincialOfficialSource, ...] = (
    ProvincialOfficialSource("北京", ("北京市", "北京"), ("beijing.gov.cn",)),
    ProvincialOfficialSource("天津", ("天津市", "天津"), ("tj.gov.cn",)),
    ProvincialOfficialSource("河北", ("河北省", "河北"), ("hebei.gov.cn",)),
    ProvincialOfficialSource("山西", ("山西省", "山西"), ("shanxi.gov.cn",)),
    ProvincialOfficialSource(
        "内蒙古",
        ("内蒙古自治区", "内蒙古"),
        ("nmg.gov.cn",),
    ),
    ProvincialOfficialSource("辽宁", ("辽宁省", "辽宁"), ("ln.gov.cn",)),
    ProvincialOfficialSource("吉林", ("吉林省", "吉林"), ("jl.gov.cn",)),
    ProvincialOfficialSource("黑龙江", ("黑龙江省", "黑龙江"), ("hlj.gov.cn",)),
    ProvincialOfficialSource(
        "上海",
        ("上海市", "上海"),
        ("shanghai.gov.cn", "sh.gov.cn"),
    ),
    ProvincialOfficialSource("江苏", ("江苏省", "江苏"), ("jiangsu.gov.cn",)),
    ProvincialOfficialSource("浙江", ("浙江省", "浙江"), ("zj.gov.cn",)),
    ProvincialOfficialSource("安徽", ("安徽省", "安徽"), ("ah.gov.cn",)),
    ProvincialOfficialSource("福建", ("福建省", "福建"), ("fujian.gov.cn",)),
    ProvincialOfficialSource("江西", ("江西省", "江西"), ("jiangxi.gov.cn",)),
    ProvincialOfficialSource("山东", ("山东省", "山东"), ("shandong.gov.cn",)),
    ProvincialOfficialSource("河南", ("河南省", "河南"), ("henan.gov.cn",)),
    ProvincialOfficialSource("湖北", ("湖北省", "湖北"), ("hubei.gov.cn",)),
    ProvincialOfficialSource("湖南", ("湖南省", "湖南"), ("hunan.gov.cn",)),
    ProvincialOfficialSource("广东", ("广东省", "广东"), ("gd.gov.cn",)),
    ProvincialOfficialSource(
        "广西",
        ("广西壮族自治区", "广西"),
        ("gxzf.gov.cn",),
    ),
    ProvincialOfficialSource("海南", ("海南省", "海南"), ("hainan.gov.cn",)),
    ProvincialOfficialSource("重庆", ("重庆市", "重庆"), ("cq.gov.cn",)),
    ProvincialOfficialSource("四川", ("四川省", "四川"), ("sc.gov.cn",)),
    ProvincialOfficialSource("贵州", ("贵州省", "贵州"), ("guizhou.gov.cn",)),
    ProvincialOfficialSource("云南", ("云南省", "云南"), ("yn.gov.cn",)),
    ProvincialOfficialSource(
        "西藏",
        ("西藏自治区", "西藏"),
        ("xizang.gov.cn",),
    ),
    ProvincialOfficialSource("陕西", ("陕西省", "陕西"), ("shaanxi.gov.cn",)),
    ProvincialOfficialSource("甘肃", ("甘肃省", "甘肃"), ("gansu.gov.cn",)),
    ProvincialOfficialSource("青海", ("青海省", "青海"), ("qinghai.gov.cn",)),
    ProvincialOfficialSource(
        "宁夏",
        ("宁夏回族自治区", "宁夏"),
        ("nx.gov.cn",),
    ),
    ProvincialOfficialSource(
        "新疆",
        ("新疆维吾尔自治区", "新疆"),
        ("xinjiang.gov.cn",),
    ),
)

PROVINCIAL_OFFICIAL_DOMAINS: tuple[str, ...] = tuple(
    domain
    for source in PROVINCIAL_OFFICIAL_SOURCES
    for domain in source.domains
)

# 国家级政策主信源（含子域，如 kjs.mof.gov.cn、fgk.chinatax.gov.cn）。
# 注意：不要用裸 gov.cn，否则会匹配全国所有 *.gov.cn 地方站，冲掉财政部结果。
# 中国政府网只用 www.gov.cn。
NATIONAL_OFFICIAL_POLICY_DOMAINS: tuple[str, ...] = (
    "mof.gov.cn",
    "chinatax.gov.cn",
    "casc.org.cn",
    "npc.gov.cn",
    "www.gov.cn",
    "stats.gov.cn",
)

# URL 安全白名单包含国家级和全部省级政府根域名。
OFFICIAL_POLICY_DOMAINS: tuple[str, ...] = (
    NATIONAL_OFFICIAL_POLICY_DOMAINS + PROVINCIAL_OFFICIAL_DOMAINS
)

# 可引用但须标明「专业参考平台，非纯官方」
SUPPLEMENTAL_DOMAINS: tuple[str, ...] = (
    "shui5.cn",
    "xinhuanet.com",
    "news.cn",
    "people.com.cn",
    "cctv.com",
    "china.com.cn",
)

_FETCH_MAX_BYTES = 512_000
_DEFAULT_FETCH_CHARS = 4000

# 政策/税法类检索优先站点
_NATIONAL_QUERY_DOMAINS: tuple[str, ...] = (
    "chinatax.gov.cn",
    "mof.gov.cn",
    "fgk.chinatax.gov.cn",
    "casc.org.cn",
    "kjs.mof.gov.cn",
    "flk.npc.gov.cn",
    "www.gov.cn",
)

# 财政收支/预算执行类优先站点（避免被税总法规、地方市政府结果挤掉）
_FISCAL_QUERY_DOMAINS: tuple[str, ...] = (
    "mof.gov.cn",
    "gks.mof.gov.cn",
    "www.gov.cn",
    "npc.gov.cn",
    "stats.gov.cn",
)

_FISCAL_DATA_QUERY_HINTS: tuple[str, ...] = (
    "财政收支",
    "财政收入",
    "财政支出",
    "财政数据",
    "财政运行",
    "财政概况",
    "国家财政",
    "全国财政",
    "季度财政",
    "预算执行",
    "一般公共预算",
    "政府性基金预算",
    "财政收支情况",
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
    try:
        port = parsed.port
    except ValueError:
        return False
    if port not in (None, 443):
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


def provincial_domains_for_region(region: str | None) -> tuple[str, ...]:
    """按显式地区参数映射省级政府根域名；无法识别则空。"""
    text = (region or "").strip()
    if not text:
        return ()
    domains: list[str] = []
    for source in PROVINCIAL_OFFICIAL_SOURCES:
        aliases = (source.name, *source.aliases)
        if any(alias in text or text in alias for alias in aliases):
            domains.extend(source.domains)
    return tuple(dict.fromkeys(domains))


def provincial_domains_for_question(
    question: str, region: str | None = None
) -> tuple[str, ...]:
    """地区参数优先；否则根据问题正文中的省级名称选择地方政府根域名。"""
    from_region = provincial_domains_for_region(region)
    if from_region:
        return from_region
    text = (question or "").strip()
    if not text:
        return ()
    domains: list[str] = []
    for source in PROVINCIAL_OFFICIAL_SOURCES:
        if any(alias in text for alias in source.aliases):
            domains.extend(source.domains)
    return tuple(dict.fromkeys(domains))


def _is_fiscal_question(question: str, topic: str | None = None) -> bool:
    """是否为财政收支/预算执行类问题。"""
    normalized = _normalize_topic(topic)
    if normalized in {"fiscal", "budget"}:
        return True
    text = question or ""
    return any(hint in text for hint in _FISCAL_DATA_QUERY_HINTS)


def official_search_domains(
    question: str, region: str | None = None, topic: str | None = None
) -> tuple[str, ...]:
    """生成提供商本轮允许检索的国家级、命中省级和补充来源域名。"""
    national = (
        _FISCAL_QUERY_DOMAINS
        if _is_fiscal_question(question, topic=topic)
        else NATIONAL_OFFICIAL_POLICY_DOMAINS
    )
    return tuple(
        dict.fromkeys(
            national
            + provincial_domains_for_question(question, region=region)
            + SUPPLEMENTAL_DOMAINS
        )
    )


def _normalize_topic(topic: str | None) -> str | None:
    """把中英文主题归一成 policy / fiscal / tax / budget / other。"""
    raw = (topic or "").strip().lower()
    if not raw:
        return None
    mapping = {
        "policy": "policy",
        "政策": "policy",
        "法规": "policy",
        "fiscal": "fiscal",
        "财政": "fiscal",
        "财政收支": "fiscal",
        "概况": "fiscal",
        "tax": "tax",
        "税收": "tax",
        "税务": "tax",
        "budget": "budget",
        "预算": "budget",
        "预算执行": "budget",
        "other": "other",
    }
    if raw in mapping:
        return mapping[raw]
    for key, value in mapping.items():
        if key in raw:
            return value
    return "other"


def _query_topic_terms(question: str, topic: str | None = None) -> str:
    """按政策或财政数据场景补充检索词，避免季度数据被法规词稀释。"""
    if _is_fiscal_question(question, topic=topic):
        # 锚定国库司/全国口径，减少地市财政局噪声
        return "财政部 国库司 全国一般公共预算 财政收支情况"
    normalized = _normalize_topic(topic)
    if normalized == "tax":
        return "税收 政策 法规"
    if normalized == "policy":
        return "政策 法规"
    return "政策 法规"


def boost_official_policy_query(
    question: str,
    *,
    region: str | None = None,
    period: str | None = None,
    topic: str | None = None,
) -> str:
    """检索词加上期间、地区与主题增强；不再拼接 site:（全网检索）。"""
    q = (question or "").strip()
    if not q:
        return q
    extras: list[str] = []
    period_s = (period or "").strip()
    if period_s and period_s not in q:
        extras.append(period_s)
    region_s = (region or "").strip()
    if region_s and region_s not in q:
        extras.append(region_s)
    extras.append(_query_topic_terms(q, topic=topic))
    return " ".join([q, *extras]).strip()


def is_safe_http_url(url: str) -> bool:
    """开网结果仅要求 https + 非 IP + 无用户信息；不抓取正文，只引用摘要。"""
    raw = (url or "").strip()
    if not raw:
        return False
    try:
        parsed = urlparse(raw)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    if parsed.username or parsed.password:
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    if port not in (None, 443):
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or _is_ip_host(host):
        return False
    return True


def sources_from_hits(hits: list[dict]) -> list[dict[str, Any]]:
    """将命中序列化为可落库/SSE 的 sources（index 从 1）。"""
    out: list[dict[str, Any]] = []
    for i, h in enumerate(hits, start=1):
        url = str(h.get("url") or "")
        host = ""
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            host = ""
        snippet = (h.get("snippet") or "").strip()
        if len(snippet) > 300:
            snippet = snippet[:300]
        out.append(
            {
                "index": i,
                "title": str(h.get("title") or "未命名"),
                "url": url,
                "snippet": snippet,
                "source_kind": str(h.get("source_kind") or "web"),
                "favicon_host": host,
                "published_at": str(h.get("published_at") or ""),
            }
        )
    return out


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
        if source_kind == "supplemental":
            label = "专业参考平台（非纯官方）"
        elif source_kind == "web":
            label = "公开网页摘要（非权威白名单）"
        else:
            label = "权威官网"
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
    """search_official_data + fetch_official_page。"""

    async def search_and_fetch(
        self,
        question: str,
        *,
        runtime: WebSearchRuntime | None = None,
        region: str | None = None,
        period: str | None = None,
        topic: str | None = None,
    ) -> dict[str, Any]:
        """单次全网检索；官方加权排序；原文抓取仍限白名单 HTTPS。"""
        rt = runtime or WebSearchRuntime.from_settings()
        query = boost_official_policy_query(
            question, region=region, period=period, topic=topic
        )
        search = await web_search_service.search(
            query,
            runtime=rt,
            max_results=rt.max_results,
            include_domains=None,
        )
        hits = self._filter_hits(search.get("hits") or [], allow_open_web=True)
        hits = self._rank_hits(
            hits, question=question, region=region, topic=topic
        )
        hits = hits[: rt.max_results]

        pages: list[dict[str, str]] = []
        fetch_n = rt.fetch_pages
        if fetch_n > 0 and hits:
            # 只抓取权威官网正文，开网摘要不发 HTTP 抓取（防 SSRF）
            official_first = [h for h in hits if h.get("source_kind") == "official"]
            to_fetch = official_first[:fetch_n]
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
        if ok and not hits and not pages:
            error = error or "全网检索未得到可用结果"
        return {
            "ok": ok and bool(hits or pages),
            "provider": search.get("provider"),
            "query": query,
            "hits": hits,
            "pages": pages,
            "sources": sources_from_hits(hits),
            "broadened": False,
            "error": None if (ok and (hits or pages)) else error,
        }

    @staticmethod
    def _filter_hits(
        raw_hits: list[dict], *, allow_open_web: bool = True
    ) -> list[dict[str, str]]:
        """过滤检索命中；开网模式可保留非白名单 https 摘要。"""
        hits: list[dict[str, str]] = []
        for item in raw_hits:
            url = item.get("url") or ""
            if is_allowed_official_url(url):
                host = (urlparse(url).hostname or "")
                kind = classify_official_host(host) or "official"
                hits.append({**item, "source_kind": kind})
                continue
            if allow_open_web and is_safe_http_url(url):
                hits.append({**item, "source_kind": "web"})
            else:
                logger.info("drop off-whitelist search hit url=%s", url[:120])
        return hits

    @staticmethod
    def _rank_hits(
        hits: list[dict[str, str]],
        *,
        question: str,
        region: str | None,
        topic: str | None,
    ) -> list[dict[str, str]]:
        """国家级/命中省级/补充来源加权；其它 *.gov.cn 仅小幅降权，不过滤。"""
        if not hits:
            return hits

        provincial_domains = provincial_domains_for_question(question, region=region)
        fiscal = _is_fiscal_question(question, topic=topic)

        def is_national_gov_host(host: str) -> bool:
            if "mof.gov.cn" in host or "chinatax.gov.cn" in host:
                return True
            if host in {"www.gov.cn", "npc.gov.cn", "stats.gov.cn"}:
                return True
            if host.endswith(".npc.gov.cn") or host.endswith(".stats.gov.cn"):
                return True
            return False

        def score(item: dict[str, str]) -> int:
            url = item.get("url") or ""
            blob = f"{item.get('title') or ''} {item.get('snippet') or ''}"
            kind = item.get("source_kind") or "web"
            try:
                host = (urlparse(url).hostname or "").lower()
            except ValueError:
                host = ""
            points = 0

            if _host_matches(host, "mof.gov.cn"):
                points += 100
            if _host_matches(host, "chinatax.gov.cn"):
                points += 95
            if _host_matches(host, "www.gov.cn"):
                points += 90
            if _host_matches(host, "stats.gov.cn"):
                points += 85
            if _host_matches(host, "npc.gov.cn"):
                points += 85

            for domain in provincial_domains:
                if _host_matches(host, domain):
                    points += 80
                    break

            if kind == "supplemental":
                points += 55
            if _host_matches(host, "news.cn") or _host_matches(host, "xinhuanet.com"):
                points += 65
            if _host_matches(host, "people.com.cn"):
                points += 60

            if fiscal:
                if "全国" in blob or "一般公共预算" in blob:
                    points += 40
                if "财政部" in blob or "国库司" in blob:
                    points += 30

            if (
                host.endswith(".gov.cn")
                and not is_national_gov_host(host)
                and not any(_host_matches(host, d) for d in provincial_domains)
            ):
                points -= 20

            if kind == "web":
                points += 10

            return points

        return sorted(hits, key=score, reverse=True)

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
