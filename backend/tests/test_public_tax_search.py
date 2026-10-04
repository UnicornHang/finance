"""权威站点检索：白名单、启发式与资料格式化。"""

from app.services.chat_service import (
    _looks_like_official_portal_query,
    _looks_like_policy_query,
    _looks_like_public_tax_query,
    _should_use_official_search,
)
from app.services.official_policy_service import (
    boost_official_policy_query,
    extract_html_text,
    format_official_policy_context,
    is_allowed_official_url,
)


def test_guangzhou_latest_tax_prefers_official_search():
    """「政策」命中制度启发时，公开税收问题仍走官网检索。"""
    q = "广州最新财务税收政策是怎样的？"
    assert _looks_like_public_tax_query(q)
    assert _looks_like_policy_query(q)
    assert _should_use_official_search(q)


def test_internal_reimburse_does_not_prefer_official_search():
    """差旅报销不走外网。"""
    q = "差旅住宿补贴怎么报？"
    assert not _should_use_official_search(q)


def test_internal_policy_is_not_public_tax():
    """差旅报销仍走企业知识库。"""
    q = "差旅住宿补贴怎么报？"
    assert _looks_like_policy_query(q)
    assert not _looks_like_public_tax_query(q)


def test_weather_is_neither_policy_nor_public_tax():
    """天气等无关问题不触发检索。"""
    q = "今天广州的天气怎么样"
    assert not _looks_like_public_tax_query(q)
    assert not _looks_like_official_portal_query(q)


def test_invoice_verify_is_portal_not_search():
    """发票查验引导官方平台，不走政策检索。"""
    q = "帮我查验这张发票真伪"
    assert _looks_like_official_portal_query(q)
    assert not _looks_like_public_tax_query(q)


def test_boost_query_pins_official_sites():
    """检索词带官方 site 限定。"""
    boosted = boost_official_policy_query("增值税税率")
    assert "增值税税率" in boosted
    assert "site:chinatax.gov.cn" in boosted
    assert "site:mof.gov.cn" in boosted


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
    assert not is_allowed_official_url("https://user:pass@www.chinatax.gov.cn/")


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
