"""
=============================================================
小红书 AI Studio - 合规审查模块 (Sprint 2)
=============================================================
小红书有严格的违禁词机制，文案踩雷会导致：限流 / 笔记不收录 / 账号降权 / 封号
本模块在 Copywriter 产出后、Art Director 之前做一道拦截

⚠️ 重要：本地词库只是第一道防线，覆盖不全。
   上线生产环境必须叠加官方内容安全 API（阿里云内容安全 / 腾讯天御）做兜底。
=============================================================
"""

import re
from typing import Dict, List


# =========================================================
#  违禁词库（按类型分类，便于给出针对性建议）
# =========================================================

# --- 1. 极限词（《广告法》明令禁止，全品类违禁）---
EXTREME_WORDS = [
    "最佳", "最好", "最大", "最高", "最低", "最便宜", "最优",
    "第一", "唯一", "首个", "首家", "顶级", "顶尖", "极致",
    "国家级", "世界级", "全球级", "全网最", "史上最", "100%",
    "绝无仅有", "独一无二", "无与伦比", "万能", "包治",
]

# --- 2. 医疗 / 功效违规词（化妆品、保健品类高危）---
MEDICAL_WORDS = [
    "根治", "治愈", "速效", "特效", "疗效", "药用", "处方",
    "排毒", "杀菌", "消炎", "抗炎", "抑菌", "祛疤", "除疤",
    "纯天然", "无添加", "无副作用", "脱敏", "抗敏",
    "防癌", "抗癌", "防病", "治病", "活血", "祛湿",
]

# --- 3. 化妆品功效违规（普通化妆品不能宣称的功效）---
COSMETIC_FUNCTION_WORDS = [
    "美白针", "瘦脸针", "溶脂", "丰胸", "壮阳", "减肥药",
    "换肤", "去皱纹", "祛斑根除", "永久脱毛",
]

# --- 4. 引流 / 营销违规 ---
MARKETING_WORDS = [
    "加微信", "加vx", "私信我", "扫码", "进群", "代购",
    "点击链接", "戳链接", "vx同号", "薇:", "微:",
]

# --- 5. 虚假宣传敏感词（需谨慎）---
EXAGGERATION_WORDS = [
    "三天见效", "七天美白", "一夜变白", "立竿见影",
    "永不复发", "终身", "永久有效",
]


BANNED_CATEGORIES = {
    "极限词（违反广告法）": EXTREME_WORDS,
    "医疗功效词": MEDICAL_WORDS,
    "化妆品违规功效": COSMETIC_FUNCTION_WORDS,
    "引流营销词": MARKETING_WORDS,
    "虚假夸大词": EXAGGERATION_WORDS,
}


# =========================================================
#  替换建议映射（命中即给出可用的安全替代词）
# =========================================================

# ---- 垂类上下文豁免：这些词在本项目的非医疗垂直中是正常用语 ----
CONTEXT_WHITELIST = {
    "healing": ["治愈"],       # 治愈语录/治愈系 → 情感内容，不是医疗宣称
}
# "治愈" 在本 App 里永远是情感内容，非医疗场景 → 全局豁免
HEALING_CONTEXT_SIGNALS = ["语录", "治愈", "温柔", "情感", "共鸣", "晚安", "深夜", "文案", "释怀", "独居", "失眠"]
# usage: 调用 check_compliance(text, context="healing") 时自动跳过上述词


REPLACEMENT_HINTS = {
    "最": "可改为「很」「超」「特别」",
    "第一": "可改为「数一数二」「排得上号」",
    "唯一": "可改为「难得」「少见」",
    "100%": "可改为「亲测有效」「我个人觉得」",
    "根治": "可改为「改善」「缓解」",
    "速效": "可改为「上手快」「见效不慢」",
    "排毒": "可改为「清爽」「焕新」",
    "纯天然": "可改为「成分温和」「植物来源」",
    "无添加": "可改为「成分简单」「精简配方」",
    "美白": "护肤类慎用，可改为「提亮」「均匀肤色」",
    "祛斑": "护肤类慎用，可改为「淡化痘印」「改善暗沉」",
    "三天见效": "可改为「坚持一段时间能看到变化」",
}


# =========================================================
#  审查主函数
# =========================================================

def check_compliance(text: str, context: str = "") -> Dict:
    """
    检查文案合规性

    Parameters
    ----------
    text : str          待检查的文案
    context : str       垂类上下文 ('knowledge'|'healing'|'')

    Returns
    -------
    dict: {safe, risk_level, violations, summary}
    """
    if not text:
        return {
            "safe": True, "risk_level": "无",
            "violations": [], "summary": "无文本可审查",
        }

    violations: List[Dict] = []
    whitelist = CONTEXT_WHITELIST.get(context, [])
    # 自动豁免：如果文案里出现了治愈系语境信号词，"治愈"不是医疗宣称
    if context == "healing" or any(s in text for s in HEALING_CONTEXT_SIGNALS):
        whitelist = list(set(whitelist + ["治愈"]))
    for category, words in BANNED_CATEGORIES.items():
        for word in words:
            if word in text and word not in whitelist:
                # 找替换建议（支持前缀匹配）
                hint = ""
                for key, h in REPLACEMENT_HINTS.items():
                    if key in word or word in key:
                        hint = h
                        break
                violations.append({
                    "word": word,
                    "category": category,
                    "hint": hint or "建议删除或换一种说法",
                })

    # 去重（同一个词只报一次）
    seen = set()
    unique = []
    for v in violations:
        if v["word"] not in seen:
            seen.add(v["word"])
            unique.append(v)
    violations = unique

    # 风险分级
    if not violations:
        risk = "无"
        safe = True
        summary = "✅ 未检测到违禁词，文案合规"
    else:
        # 引流词/医疗词属高危
        high_risk_cats = {"引流营销词", "医疗功效词", "化妆品违规功效"}
        has_high = any(v["category"] in high_risk_cats for v in violations)
        if has_high:
            risk, safe = "高", False
        elif len(violations) >= 3:
            risk, safe = "中", False
        else:
            risk, safe = "低", False
        summary = (
            f"⚠️ 检测到 {len(violations)} 个违禁词，风险等级：{risk}。"
            f"发布前建议修改。"
        )

    return {
        "safe": safe,
        "risk_level": risk,
        "violations": violations,
        "summary": summary,
    }


def format_compliance_report(result: Dict) -> str:
    """把审查结果格式化成 Markdown，用于 UI 展示 / Agent 阅读"""
    lines = [f"### 🛡️ 合规审查\n", result["summary"], ""]
    if result["violations"]:
        lines.append("| 违禁词 | 类型 | 修改建议 |")
        lines.append("|---|---|---|")
        for v in result["violations"]:
            lines.append(f"| `{v['word']}` | {v['category']} | {v['hint']} |")
    return "\n".join(lines)


def auto_sanitize(text: str) -> str:
    """
    极限词的保守自动替换（仅处理最常见、替换无歧义的）
    注意：不做激进替换，避免破坏文意。复杂的交给 Copywriter 重写
    """
    safe_replacements = {
        "100%": "亲测",
        "全网最低": "价格很美丽",
        "史上最": "非常",
        "绝无仅有": "很难得",
        "独一无二": "很特别",
    }
    for bad, good in safe_replacements.items():
        text = text.replace(bad, good)
    return text
