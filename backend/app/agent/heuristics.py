"""意图分类失败时的保守回退启发。

主路径由 LLM 分类；仅当 JSON 无效、置信度过低或演示模式无结构化输出时使用。
不得作为线上主路由。
"""

# 粗粒度启发：命中则更倾向走制度问答 + RAG
_POLICY_HINTS = (
    "差旅",
    "补贴",
    "报销",
    "制度",
    "标准",
    "住宿",
    "餐补",
    "交通",
    "合规",
    "政策",
    "规定",
    "审批",
    "多少钱",
    "怎么报",
    "一线城市",
    "二线",
)

# 公开财税：走外网检索，而不是企业知识库
_PUBLIC_TAX_HINTS = (
    "税率",
    "增值税",
    "所得税",
    "企业所得税",
    "个人所得税",
    "个税",
    "税收优惠",
    "税务优惠",
    "加计扣除",
    "留抵退税",
    "出口退税",
    "进项",
    "销项",
    "征收率",
    "印花税",
    "附加税",
    "消费税",
    "税务总局",
    "国家税务总局",
    "财政部",
    "财税",
    "税总",
    "汇算清缴",
    "数电票",
    "电子发票",
    "小微企业",
    "高新",
    "研发费用",
    "地区优惠",
    "大湾区",
    "税收政策",
    "税收",
    "最新政策",
    "政策法规",
    "免税",
    "即征即退",
    "核定征收",
    "税务局",
    "法规库",
    "会计准则",
    "新规",
    "文号",
    "会计司",
    "法律法规",
    "政策文件",
    "法规",
)

_INTERNAL_REIMBURSE_HINTS = (
    "差旅",
    "补贴",
    "报销",
    "住宿",
    "餐补",
    "怎么报",
)

_PORTAL_HINTS = (
    "发票真伪",
    "查验发票",
    "验真",
    "工商信息",
    "信用公示",
    "企业公示",
    "裁判文书",
    "gsxt",
    "wenshu",
    "inv-veri",
)


def looks_like_policy_query(text: str) -> bool:
    """用户问题是否像企业内部制度/标准查询。"""
    t = (text or "").strip()
    if not t:
        return False
    return any(k in t for k in _POLICY_HINTS)


def looks_like_internal_reimburse(text: str) -> bool:
    """是否在问本公司差旅/报销标准（必须走知识库）。"""
    t = (text or "").strip()
    if not t:
        return False
    return any(k in t for k in _INTERNAL_REIMBURSE_HINTS)


def looks_like_official_portal_query(text: str) -> bool:
    """是否在要发票查验/公示/文书等官方业务入口，而不是政策检索。"""
    t = (text or "").strip().lower()
    if not t:
        return False
    return any(k in t for k in _PORTAL_HINTS)


def looks_like_public_tax_query(text: str) -> bool:
    """用户问题是否像公开财税政策/税率/法规查询。"""
    t = (text or "").strip()
    if not t:
        return False
    if looks_like_official_portal_query(t):
        return False
    return any(k in t for k in _PUBLIC_TAX_HINTS)


_FOLLOWUP_HINTS = (
    "那",
    "这个",
    "这些",
    "还有",
    "继续",
    "刚才",
    "上面",
    "一线",
    "二线",
    "具体",
    "呢",
    "然后",
    "标准呢",
)


_CONFIRM_HINTS = (
    "确认归档",
    "确定归档",
    "帮我存进去",
    "帮我归档",
    "确认入库",
    "帮我确认归档",
)


def looks_like_confirm_archive(text: str) -> bool:
    """用户是否在对话里要求把当前待办单据确认归档。"""
    t = (text or "").strip()
    if not t:
        return False
    return any(k in t for k in _CONFIRM_HINTS)


def looks_like_followup(text: str) -> bool:
    """短追问或省略主语，可能应继承上一轮制度/公开财税白名单。"""
    t = (text or "").strip()
    if not t:
        return False
    if looks_like_official_portal_query(t):
        return False
    if looks_like_confirm_archive(t):
        return False
    if any(k in t for k in _FOLLOWUP_HINTS):
        return True
    if len(t) <= 20 and t.endswith(("呢", "吗", "？", "?")):
        return True
    return False


def should_use_official_search(text: str) -> bool:
    """公开财税检索优先于弱相关知识库命中。

    「政策」会出现在制度启发里，差旅文档也常被召回；
    问广州税收政策时不能因此锁进「知识库暂无」。
    """
    if not looks_like_public_tax_query(text):
        return False
    if not looks_like_internal_reimburse(text):
        return True
    return any(
        k in text
        for k in ("税率", "税收政策", "税收优惠", "最新政策", "新规", "税务总局", "财政部")
    )
