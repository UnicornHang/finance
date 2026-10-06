"""权威站点检索：白名单、启发回退与资料格式化。"""

import pytest

from app.agent.heuristics import (
    looks_like_official_portal_query,
    looks_like_policy_query,
    looks_like_public_tax_query,
    should_use_official_search,
)
from app.agent.router import Intent, heuristic_intent
from app.services.official_policy_service import (
    OfficialPolicyService,
    boost_official_policy_query,
    extract_html_text,
    format_official_policy_context,
    is_allowed_official_url,
    is_safe_http_url,
    official_search_domains,
    provincial_domains_for_question,
    provincial_domains_for_region,
    sources_from_hits,
)

PROVINCIAL_DOMAIN_CASES = (
    ("北京", "beijing.gov.cn"),
    ("天津", "tj.gov.cn"),
    ("河北", "hebei.gov.cn"),
    ("山西", "shanxi.gov.cn"),
    ("内蒙古", "nmg.gov.cn"),
    ("辽宁", "ln.gov.cn"),
    ("吉林", "jl.gov.cn"),
    ("黑龙江", "hlj.gov.cn"),
    ("上海", "shanghai.gov.cn"),
    ("上海", "sh.gov.cn"),
    ("江苏", "jiangsu.gov.cn"),
    ("浙江", "zj.gov.cn"),
    ("安徽", "ah.gov.cn"),
    ("福建", "fujian.gov.cn"),
    ("江西", "jiangxi.gov.cn"),
    ("山东", "shandong.gov.cn"),
    ("河南", "henan.gov.cn"),
    ("湖北", "hubei.gov.cn"),
    ("湖南", "hunan.gov.cn"),
    ("广东", "gd.gov.cn"),
    ("广西", "gxzf.gov.cn"),
    ("海南", "hainan.gov.cn"),
    ("重庆", "cq.gov.cn"),
    ("四川", "sc.gov.cn"),
    ("贵州", "guizhou.gov.cn"),
    ("云南", "yn.gov.cn"),
    ("西藏", "xizang.gov.cn"),
    ("陕西", "shaanxi.gov.cn"),
    ("甘肃", "gansu.gov.cn"),
    ("青海", "qinghai.gov.cn"),
    ("宁夏", "nx.gov.cn"),
    ("新疆", "xinjiang.gov.cn"),
)


def test_guangzhou_latest_tax_prefers_official_search():
    """「政策」命中制度启发时，公开税收问题仍走官网检索。"""
    q = "广州最新财务税收政策是怎样的？"
    assert looks_like_public_tax_query(q)
    assert looks_like_policy_query(q)
    assert should_use_official_search(q)
    assert heuristic_intent(q) == Intent.PUBLIC_TAX


def test_provincial_quarterly_finance_prefers_official_search():
    """地方季度财政收支属于公开官方数据，必须走官网检索。"""
    q = "2026广东省一季度财政"

    assert looks_like_public_tax_query(q)
    assert should_use_official_search(q)
    assert heuristic_intent(q) == Intent.PUBLIC_TAX
    assert "财政部 国库司 全国一般公共预算" in boost_official_policy_query(q)


def test_national_fiscal_overview_uses_fiscal_boost_not_policy_terms():
    """「国家财政」应按财政数据检索，且不再拼接 site: 限定。"""
    q = "2025年国家财政"
    boosted = boost_official_policy_query(q)
    assert "财政部 国库司 全国一般公共预算" in boosted
    assert "政策 法规" not in boosted
    assert "site:" not in boosted
    domains = official_search_domains(q)
    assert "www.gov.cn" in domains
    assert "gov.cn" not in domains or "www.gov.cn" in domains
    assert "mof.gov.cn" in domains


def test_region_period_still_in_boost_without_site():
    """地区/期间仍进入检索词，但不加 site:。"""
    boosted = boost_official_policy_query(
        "财政收支", region="广东", period="2026年一季度", topic="fiscal"
    )
    assert "2026年一季度" in boosted
    assert "广东" in boosted or "财政收支" in boosted
    assert "site:gd.gov.cn" not in boosted
    assert "site:" not in boosted


def test_bare_gov_cn_does_not_whitelist_city_portals():
    """裸 gov.cn 不再放行安康等无关地市站。"""
    assert is_allowed_official_url(
        "https://www.gov.cn/lianbo/202601/content_7056673.htm"
    )
    assert not is_allowed_official_url("https://www.ak.gov.cn/caijing/2025.html")
    assert is_allowed_official_url(
        "https://gks.mof.gov.cn/tongjishuju/202601/t20260130_3982923.htm"
    )


def test_internal_reimburse_does_not_prefer_official_search():
    """差旅报销不走外网。"""
    q = "差旅住宿补贴怎么报？"
    assert not should_use_official_search(q)
    assert heuristic_intent(q) == Intent.POLICY_QUERY


def test_internal_policy_is_not_public_tax():
    """差旅报销仍走企业知识库。"""
    q = "差旅住宿补贴怎么报？"
    assert looks_like_policy_query(q)
    assert not looks_like_public_tax_query(q)


def test_weather_is_neither_policy_nor_public_tax():
    """天气等无关问题不触发检索。"""
    q = "今天广州的天气怎么样"
    assert not looks_like_public_tax_query(q)
    assert not looks_like_official_portal_query(q)
    assert heuristic_intent(q) == Intent.CHITCHAT


def test_invoice_verify_is_portal_not_search():
    """发票查验引导官方平台，不走政策检索。"""
    q = "帮我查验这张发票真伪"
    assert looks_like_official_portal_query(q)
    assert not looks_like_public_tax_query(q)
    assert heuristic_intent(q) == Intent.OFFICIAL_PORTAL


def test_boost_query_pins_official_sites():
    """检索词含主题增强，但不拼接 site: 限定。"""
    boosted = boost_official_policy_query("增值税税率")
    assert "增值税税率" in boosted
    assert "政策 法规" in boosted
    assert "site:" not in boosted


@pytest.mark.parametrize(("region", "domain"), PROVINCIAL_DOMAIN_CASES)
def test_all_mainland_provincial_domains_are_official(region: str, domain: str):
    """大陆 31 个省级行政区的政府根域名及其子域名均属于官方来源。"""
    assert is_allowed_official_url(f"https://data.{domain}/{region}")


def test_boost_query_adds_only_matched_provincial_domains():
    """省级问题仍带主题增强；域名映射单独由 provincial_domains_for_question 提供。"""
    boosted = boost_official_policy_query("广东省最新财税政策")

    assert "广东省最新财税政策" in boosted
    assert "site:" not in boosted
    assert provincial_domains_for_question("广东省最新财税政策") == ("gd.gov.cn",)


def test_shanghai_query_supports_portal_and_department_roots():
    """上海门户和委办局使用的两套政府根域名都参与检索。"""
    domains = official_search_domains("上海市财政局最新政策")

    assert "shanghai.gov.cn" in domains
    assert "sh.gov.cn" in domains
    assert "gd.gov.cn" not in domains


def test_national_query_does_not_add_provincial_domains():
    """未指定地区时维持国家级信源，不加入无关地方域名。"""
    boosted = boost_official_policy_query("最新增值税政策")
    domains = official_search_domains("最新增值税政策")

    assert "site:" not in boosted
    assert "gd.gov.cn" not in domains
    assert "chinatax.gov.cn" in domains


def test_region_param_selects_provincial_domain():
    """显式 region 优先驱动省级域名与检索增强。"""
    assert "gd.gov.cn" in provincial_domains_for_region("广东")
    domains = official_search_domains("财政收支", region="广东")
    assert "gd.gov.cn" in domains
    assert "sh.gov.cn" not in domains
    boosted = boost_official_policy_query(
        "财政收支",
        region="广东",
        period="2026年一季度",
        topic="fiscal",
    )
    assert "site:" not in boosted
    assert "2026年一季度" in boosted
    assert "广东" in boosted
    assert "财政部 国库司 全国一般公共预算" in boosted


def test_region_param_overrides_unrelated_question_text():
    """正文无省份时，仅靠 region 仍可追加省级站点。"""
    assert provincial_domains_for_question("财政收支", region="上海") == (
        "shanghai.gov.cn",
        "sh.gov.cn",
    )


def test_whitelist_allows_gov_subdomains():
    """税总法规库、会计司属于白名单。"""
    assert is_allowed_official_url("https://fgk.chinatax.gov.cn/zcfgk/index")
    assert is_allowed_official_url("https://kjs.mof.gov.cn/zhengcefabu/")
    assert is_allowed_official_url("https://www.shui5.cn/a.html")


def test_whitelist_rejects_ssrf_shapes():
    """拒绝 http、IP、非白名单域名。"""
    assert not is_allowed_official_url("http://www.chinatax.gov.cn/")
    assert not is_allowed_official_url("https://127.0.0.1/")
    assert not is_allowed_official_url("https://example.com/")
    assert not is_allowed_official_url("https://gd.gov.cn.example.com/")
    assert not is_allowed_official_url("https://user:pass@www.chinatax.gov.cn/")


def test_url_helpers_reject_invalid_port():
    """非法端口（如 :bad）须拒绝，避免 urlparse.port 抛错穿透。"""
    bad = "https://example.com:bad/path?ref=mof.gov.cn"
    assert not is_allowed_official_url(bad)
    assert not is_safe_http_url(bad)


def test_rank_hits_does_not_boost_spoofed_official_in_query():
    """官方加权只看 hostname，不因 URL 查询串含 gov.cn 而加分。"""
    hits = [
        {
            "title": "伪造",
            "url": "https://evil.example.com/page?ref=mof.gov.cn",
            "snippet": "",
            "source_kind": "web",
        },
        {
            "title": "真财政部",
            "url": "https://www.mof.gov.cn/fiscal.htm",
            "snippet": "",
            "source_kind": "official",
        },
    ]
    ranked = OfficialPolicyService._rank_hits(hits, question="财政", region=None, topic=None)
    assert ranked[0]["url"].startswith("https://www.mof.gov.cn")


def test_format_context_marks_web_broadened():
    """开网摘要须标明非权威白名单，不得冒充权威官网。"""
    text = format_official_policy_context(
        {
            "ok": True,
            "hits": [
                {
                    "title": "新华社稿",
                    "url": "https://www.news.cn/a",
                    "snippet": "全国一般公共预算收入216045亿元",
                    "source_kind": "web",
                }
            ],
            "pages": [],
        }
    )
    assert "公开网页摘要" in text
    assert "216045" in text


def test_sources_from_hits_indexes_and_favicon():
    """sources 序列化 index、favicon_host 与 snippet 截断。"""
    sources = sources_from_hits(
        [
            {
                "title": "财政部",
                "url": "https://www.mof.gov.cn/a",
                "snippet": "x" * 500,
                "source_kind": "official",
            },
            {
                "title": "媒体",
                "url": "https://www.news.cn/b",
                "snippet": "短",
                "source_kind": "web",
            },
        ]
    )
    assert sources[0]["index"] == 1
    assert sources[0]["favicon_host"] == "www.mof.gov.cn"
    assert len(sources[0]["snippet"]) <= 300
    assert sources[1]["index"] == 2


@pytest.mark.asyncio
async def test_search_and_fetch_always_open_web(monkeypatch):
    """始终 include_domains=None，一次调用即可混入官方与开网结果。"""
    from app.services.web_search_service import WebSearchRuntime

    calls: list[dict] = []

    async def fake_search(query, *, runtime=None, max_results=None, include_domains=None):
        calls.append({"query": query, "include_domains": include_domains})
        return {
            "ok": True,
            "provider": "bocha",
            "query": query,
            "hits": [
                {
                    "title": "广州审计转载",
                    "url": "https://www.gz.gov.cn/audit.htm",
                    "snippet": "审计报告",
                },
                {
                    "title": "财政部收支",
                    "url": "https://www.mof.gov.cn/fiscal.htm",
                    "snippet": "全国一般公共预算",
                },
                {
                    "title": "新华网",
                    "url": "https://www.news.cn/finance/2025.htm",
                    "snippet": "216045亿元",
                },
            ],
            "error": None,
        }

    monkeypatch.setattr(
        "app.services.official_policy_service.web_search_service.search",
        fake_search,
    )
    svc = OfficialPolicyService()
    rt = WebSearchRuntime(
        enabled=True,
        provider="bocha",
        api_key="x",
        base_url="",
        timeout=5,
        max_results=8,
        fetch_pages=0,
        fetch_max_chars=1000,
    )
    result = await svc.search_and_fetch("2025年国家财政", runtime=rt)
    assert len(calls) == 1
    assert calls[0]["include_domains"] is None
    assert "site:" not in (calls[0]["query"] or "")
    assert result["ok"] is True
    assert result["hits"][0]["url"].startswith("https://www.mof.gov.cn")
    assert len(result["sources"]) == len(result["hits"])
    assert result["sources"][0]["index"] == 1


def test_format_context_marks_supplemental_and_pages():
    """税屋标明参考平台，原文单独成段。"""
    text = format_official_policy_context(
        {
            "ok": True,
            "hits": [
                {
                    "title": "税屋转载",
                    "url": "https://www.shui5.cn/a",
                    "snippet": "摘要",
                    "source_kind": "supplemental",
                }
            ],
            "pages": [
                {
                    "title": "财政部公告",
                    "url": "https://www.mof.gov.cn/a",
                    "text": "增值税征收率调整",
                }
            ],
        }
    )
    assert "专业参考平台" in text
    assert "【原文1】" in text
    assert "增值税征收率调整" in text


def test_format_context_on_failure_forbids_invention():
    """检索失败时明确禁止编造。"""
    text = format_official_policy_context(
        {"ok": False, "hits": [], "pages": [], "error": "未配置 WEB_SEARCH_API_KEY"}
    )
    assert "未配置 WEB_SEARCH_API_KEY" in text
    assert "不得编造" in text


def test_extract_html_text_strips_script():
    """正文抽取去掉脚本。"""
    html = "<html><script>alert(1)</script><title>T</title><p>政策正文</p></html>"
    text = extract_html_text(html, max_chars=200)
    assert "政策正文" in text
    assert "alert" not in text
