"""
=============================================================
小红书 AI Studio - 图像 Prompt 模板库 (Sprint 1 收尾)
=============================================================
解决问题：v1.2 之前 Art Director 临场拍脑袋写 prompt，质量不稳定。
本模块按品类预置经过调优的 prompt 骨架，Art Director 只需"填空 + 微调"。

每个品类提供：
  · base       —— 该品类通用的画面风格底座
  · negative   —— 负向词（避免 AI 味、避免文字）
  · 推荐模板   —— 该品类适合哪个海报模板
=============================================================
"""

# 全局通用负向词（所有品类都要带）
GLOBAL_NEGATIVE = (
    "no text, no letters, no words, no typography, no watermark, "
    "no logo, low quality, distorted, deformed hands, extra fingers, "
    "oversaturated, plastic skin, overexposed, blurry, ugly"
)


PROMPT_LIBRARY = {
    # ---------- 穿搭 ----------
    "穿搭": {
        "keywords": ["穿搭", "衣服", "大衣", "外套", "裙子", "OOTD", "搭配", "时尚"],
        "base": (
            "fashionable asian woman wearing stylish {detail}, "
            "candid street style photography, soft natural daylight, "
            "film grain texture, minimalist urban background, "
            "natural skin texture, elegant composition, "
            "instagram aesthetic, warm color grading"
        ),
        "recommended_template": "top_label",
    },

    # ---------- 护肤 / 美妆 ----------
    "护肤": {
        "keywords": ["护肤", "精华", "面膜", "化妆", "美妆", "保养", "面霜", "防晒"],
        "base": (
            "elegant skincare product flat lay {detail}, "
            "soft diffused studio light, clean minimalist background, "
            "fresh dewy aesthetic, pastel color palette, "
            "delicate composition with negative space, "
            "high-end cosmetic photography, gentle shadows"
        ),
        "recommended_template": "center_bold",
    },

    # ---------- 美食 / 食谱 ----------
    "美食": {
        "keywords": ["美食", "食谱", "早餐", "做法", "菜", "甜品", "下厨", "探店"],
        "base": (
            "appetizing food photography {detail}, "
            "warm natural window light, rustic wooden table, "
            "shallow depth of field, cozy home kitchen vibe, "
            "fresh ingredients styling, inviting warm tones, "
            "overhead or 45-degree angle, foodie aesthetic"
        ),
        "recommended_template": "center_bold",
    },

    # ---------- 旅行 ----------
    "旅行": {
        "keywords": ["旅行", "旅游", "攻略", "景点", "打卡", "出行", "周末去哪"],
        "base": (
            "breathtaking travel scenery {detail}, "
            "golden hour cinematic lighting, wide atmospheric landscape, "
            "film photography aesthetic, dreamy soft focus, "
            "vivid but natural color grading, sense of wanderlust"
        ),
        "recommended_template": "minimalist",
    },

    # ---------- 家居 / 好物 ----------
    "家居": {
        "keywords": ["家居", "好物", "收纳", "出租屋", "改造", "装修", "宅家", "ins风"],
        "base": (
            "cozy aesthetic home interior {detail}, "
            "warm ambient lighting, scandinavian minimalist style, "
            "soft natural light through window, tidy organized space, "
            "ins style home decor, comfortable lived-in atmosphere"
        ),
        "recommended_template": "top_label",
    },

    # ---------- 学习 / 职场 ----------
    "职场": {
        "keywords": ["学习", "考试", "考公", "职场", "效率", "备考", "干货", "笔记"],
        "base": (
            "aesthetic study desk flat lay {detail}, "
            "bright clean natural light, organized stationery, "
            "minimalist productivity vibe, notebook and coffee, "
            "calm focused atmosphere, soft neutral tones"
        ),
        "recommended_template": "magazine_cover",
    },

    # ---------- 健身 / 减脂 ----------
    "健身": {
        "keywords": ["健身", "减脂", "减肥", "运动", "瑜伽", "塑形", "身材"],
        "base": (
            "energetic fitness lifestyle scene {detail}, "
            "bright airy natural light, clean modern gym or home setting, "
            "healthy active atmosphere, fresh motivating tones, "
            "dynamic but elegant composition"
        ),
        "recommended_template": "center_bold",
    },
}

# 兜底（无法归类时）
DEFAULT_PROMPT = {
    "base": (
        "aesthetic lifestyle photography {detail}, "
        "soft natural light, clean minimalist composition, "
        "instagram style, warm pleasant color grading, "
        "high quality, elegant atmosphere"
    ),
    "recommended_template": "center_bold",
}


def classify_topic(topic: str) -> str:
    """根据选题关键词归类到某个品类，返回品类名（找不到返回 '默认'）"""
    for category, conf in PROMPT_LIBRARY.items():
        for kw in conf["keywords"]:
            if kw in topic:
                return category
    return "默认"


def build_image_prompt(topic: str, detail: str = "") -> dict:
    """
    根据选题构造图像 prompt

    Returns
    -------
    {
        "category": "穿搭",
        "prompt": "完整的英文正向 prompt",
        "negative": "负向词",
        "recommended_template": "top_label",
    }
    """
    category = classify_topic(topic)
    conf = PROMPT_LIBRARY.get(category, DEFAULT_PROMPT)

    base = conf["base"]
    # detail 留空时去掉占位符
    if detail:
        prompt = base.replace("{detail}", detail)
    else:
        prompt = base.replace("{detail}", "").replace("  ", " ")

    return {
        "category": category,
        "prompt": prompt + ", " + GLOBAL_NEGATIVE.split(",")[0],  # 正向里也提一句 no text
        "negative": GLOBAL_NEGATIVE,
        "recommended_template": conf["recommended_template"],
    }


def get_prompt_guide_for_llm() -> str:
    """生成给 Art Director 看的 prompt 模板说明"""
    lines = ["图像 Prompt 品类模板库（系统会根据选题自动匹配，你可在此基础上微调 {detail} 部分）："]
    for cat, conf in PROMPT_LIBRARY.items():
        lines.append(f"  · {cat}: 推荐模板 `{conf['recommended_template']}`")
    return "\n".join(lines)
