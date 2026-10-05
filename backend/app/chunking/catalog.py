"""给管理端展示的切分策略说明（面向业务用户，避免术语堆砌）。"""

from __future__ import annotations

from typing import Any


def chunk_strategy_catalog() -> list[dict[str, Any]]:
    """上传弹窗卡片数据。"""
    return [
        {
            "value": "parent_child",
            "label": "精确查找条款",
            "recommended": True,
            "suited": "报销、差旅、审批等制度问答",
            "how": "先聚合长父块，再切成短子块用于检索；命中子块后用父块回答。",
            "example": "检索命中「住宿上限」子块 → 注入包含前后条款的父块",
            "cost_hint": "存储略多，检索更准",
            "visual": ["短块检索", "长块回答"],
        },
        {
            "value": "structure",
            "label": "按章节标题切开",
            "recommended": False,
            "suited": "带标题的 Markdown / Word 制度",
            "how": "读取 Word 标题样式、Markdown 标题和章节编号；每个标题强制从新块开始。",
            "example": "# 差旅 → 一块；## 住宿 → 另一块",
            "cost_hint": "不额外调用模型",
            "visual": ["标题A", "标题B", "标题C"],
        },
        {
            "value": "recursive",
            "label": "按段落长度切开",
            "recommended": False,
            "suited": "没有标题的纯文本、通知、纪要",
            "how": "能放进一段就合并，放不下就切开；相邻两块留一点重叠，减少一句话被劈开。",
            "example": "三段短通知合成一块；超长附件再按字数切开",
            "cost_hint": "最快、最省",
            "visual": ["段1+段2", "段3+重叠"],
        },
        {
            "value": "semantic",
            "label": "按话题变化切开",
            "recommended": False,
            "suited": "标题不全、东一句西一句的长文",
            "how": "计算相邻句向量距离，在话题距离峰值处断开；失败会明确标记降级。",
            "example": "前面都在讲住宿标准，后面改讲合同盖章 → 自动分成两块",
            "cost_hint": "索引更慢，会多用一次 Embedding",
            "visual": ["同一话题", "话题跳变", "新块"],
        },
    ]
