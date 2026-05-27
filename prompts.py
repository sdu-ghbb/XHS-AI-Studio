"""
=============================================================
小红书 AI Studio - 图像 Prompt 模板库 (v2.1 三层架构)
=============================================================
Layer 1 — STYLE 风格层: 视觉风格/镜头/画质/艺术家参照 (固定,12 style_key)
Layer 2 — SEMANTIC 语义层: 选题实体/场景/物件 (动态,从 subject_library 匹配)
Layer 3 — EMOTION 情绪层: 色调/光线/构图/空间感 (healing 必有,knowledge 用默认)

用法:
    result = build_image_prompt(
        vertical="healing",
        style_key="dreamy_landscape",
        topic="写给深夜失眠的北漂打工人",
        mood="深夜共鸣",
        user_detail="雨夜车窗外的城市灯光",
    )
=============================================================
"""

import random

from emotion_lexicon import EMOTION_LEXICON, MOOD_TO_EMOTION
from subject_library import SUBJECT_LIBRARY, match_subject


# =========================================================
# 全局通用负向词
# =========================================================

GLOBAL_NEGATIVE = (
    "no text, no letters, no words, no typography, no watermark, "
    "no logo, no people, no faces, no human figures, "
    "low quality, distorted, ugly, oversaturated, blurry"
)


# =========================================================
# Layer 1: STYLE — 12 个固定风格，每个 400+ 字符
# =========================================================

STYLE_LIBRARY = {

    # ---- knowledge 专属 ----
    "minimalist_illustration": {
        "label": "极简插画风",
        "vertical": "knowledge",
        "base": (
            "minimalist flat vector illustration, clean off-white background, "
            "single bold focal element centered in frame, "
            "soft pastel accent colors (sage green #B2C9AB, dusty pink #D4A5A5, warm beige #E8D5B7), "
            "geometric composition with intentional negative space, "
            "academic notebook aesthetic with subtle grid lines, "
            "modern editorial design, Scandinavian graphic style"
        ),
        "default_subject": (
            "abstract conceptual shapes floating in balanced arrangement"
        ),
        "tech_specs": (
            "vector art style, crisp clean lines, flat colors, "
            "8K resolution poster, professional graphic design, "
            "in the style of Malika Favre and Tom Haugomat, "
            "Xiaohongshu cover art compatible, 3:4 aspect ratio composition"
        ),
    },

    "abstract_concept": {
        "label": "抽象概念图",
        "vertical": "knowledge",
        "base": (
            "abstract conceptual art, soft gradient background from cream to pale blue, "
            "floating translucent geometric shapes (circles, triangles, hexagons), "
            "subtle grain texture overlay, modern infographic aesthetic, "
            "professional yet warm, elegant use of negative space, "
            "layered depth with varying opacity"
        ),
        "default_subject": (
            "interconnected nodes and abstract shapes suggesting knowledge networks"
        ),
        "tech_specs": (
            "high-end editorial illustration, museum-quality abstract art, "
            "professional color grading, 8K resolution, "
            "in the style of contemporary data visualization artists, "
            "Xiaohongshu cover art compatible, balanced 3:4 layout"
        ),
    },

    "desk_flatlay": {
        "label": "学习桌面俯拍",
        "vertical": "knowledge",
        "base": (
            "aesthetic study desk flatlay overhead view, "
            "warm wooden table surface with natural grain, "
            "soft diffused window light from upper left, "
            "shallow depth of field focusing on central items, "
            "tidy organized arrangement with breathing room, "
            "calm focused atmosphere, film摄影 aesthetic"
        ),
        "default_subject": (
            "open notebook with neat handwritten notes, vintage fountain pen, "
            "ceramic coffee cup with delicate steam, small succulent plant"
        ),
        "tech_specs": (
            "shot on medium format film, Fuji Pro 400H color profile, "
            "soft natural lighting, f/2.8 shallow DOF, "
            "Instagram flatlay aesthetic, 8K resolution, "
            "no human hands visible in frame"
        ),
    },

    "notebook_paper": {
        "label": "笔记本纸张风",
        "vertical": "knowledge",
        "base": (
            "aged cream paper texture background, subtle line guides, "
            "vintage academic feel with deckle edge, "
            "warm directional light casting soft shadows, "
            "shallow depth of field with foreground blur, "
            "minimalist composition with abundant negative space, "
            "quiet library atmosphere"
        ),
        "default_subject": (
            "elegant handwritten notes in dark ink, "
            "small botanical specimen pressed between pages"
        ),
        "tech_specs": (
            "analog film aesthetic, Portra 400 color rendering, "
            "macro photography detail, 8K resolution scan, "
            "tactile paper texture, nostalgic scholarly mood"
        ),
    },

    # ---- healing 专属 ----
    "dreamy_landscape": {
        "label": "梦幻风景",
        "vertical": "healing",
        "base": (
            "dreamy cinematic landscape at golden hour, "
            "soft warm bokeh throughout frame, melancholic painterly aesthetic, "
            "muted warm tones (amber, peach, dusty rose), "
            "atmospheric haze creating depth layers, "
            "wide empty composition with 60% negative space, "
            "evocative emotional atmosphere, slow shutter effect"
        ),
        "default_subject": (
            "rolling hills or distant water at golden hour, soft mist"
        ),
        "tech_specs": (
            "shot on medium format film, Kodak Portra 800 pushed one stop, "
            "anamorphic lens flare, cinematic color grading, "
            "8K resolution, editorial photography for The New York Times Magazine, "
            "in the style of fine art landscape photographers"
        ),
    },

    "night_city": {
        "label": "夜晚城市远景",
        "vertical": "healing",
        "base": (
            "distant city lights viewed from high vantage at blue hour, "
            "blurred bokeh of skyscraper windows creating abstract light pattern, "
            "soft purple and warm orange color palette, "
            "rain-streaked window in foreground as framing device, "
            "lonely poetic urban mood, cinematic wide composition, "
            "no specific recognizable buildings"
        ),
        "default_subject": (
            "distant skyline with scattered warm-lit windows, "
            "reflection of lights on wet surface"
        ),
        "tech_specs": (
            "shot on Sony A7R5 with 85mm f/1.4, wide open aperture, "
            "cinematic color grading in DaVinci Resolve, teal-orange split tone, "
            "Blade Runner 2049 visual reference, 8K resolution, "
            "editorial photography, evocative urban solitude"
        ),
    },

    "window_light": {
        "label": "窗边光影",
        "vertical": "healing",
        "base": (
            "soft morning light streaming through window, "
            "casting gentle shadow patterns on textured wall, "
            "peaceful interior corner with minimal furnishings, "
            "warm neutral tones (cream, warm gray, pale wood), "
            "quiet contemplative moment frozen in time, "
            "dust particles floating in light beam, Vermeer lighting quality"
        ),
        "default_subject": (
            "empty wooden chair by window, lace curtain gently moving, "
            "small vase with single dried flower"
        ),
        "tech_specs": (
            "natural light only, large window diffusion, "
            "shot on Fuji GFX 100S medium format, f/5.6 for detail, "
            "painterly rendering, 8K resolution, "
            "in the style of Dutch Golden Age interior paintings, "
            "timeless quiet atmosphere"
        ),
    },

    "abstract_emotion": {
        "label": "抽象情绪色彩",
        "vertical": "healing",
        "base": (
            "abstract emotional atmosphere expressed through color alone, "
            "painterly smooth color gradient transitions, "
            "soft brush strokes with visible texture, "
            "dreamy ethereal mood, layered translucent washes, "
            "no specific objects or forms, pure emotional expression through color"
        ),
        "default_subject": (
            "gradient of muted tones blending into each other, "
            "suggesting emotional states without literal representation"
        ),
        "tech_specs": (
            "in the style of Mark Rothko and Helen Frankenthaler, "
            "color field painting aesthetic, museum-quality abstract art, "
            "8K resolution scan of canvas texture, professional color grading"
        ),
    },

    "moonlit_scene": {
        "label": "月光场景",
        "vertical": "healing",
        "base": (
            "serene moonlit night scene, soft silver-blue moonlight, "
            "calm still water reflecting moon and stars, "
            "distant mountain silhouettes at horizon, "
            "deep indigo and warm cream two-tone palette, "
            "minimalist painterly composition, peaceful solitude, "
            "dreamlike quality with slight haze"
        ),
        "default_subject": (
            "full moon low on horizon, its reflection path on still water, "
            "silhouette of single pine tree at frame edge"
        ),
        "tech_specs": (
            "long exposure photography, 30 second shutter, "
            "shot on Hasselblad X2D medium format, natural moonlight only, "
            "8K resolution, editorial nature photography, "
            "in the style of Michael Kenna, timeless contemplative mood"
        ),
    },

    # ---- 通用（两个垂类都可用）----
    "soft_gradient": {
        "label": "柔和渐变",
        "vertical": "universal",
        "base": (
            "smooth ethereal gradient background, soft color transitions, "
            "minimalist abstract composition, single central focus area, "
            "dreamy bokeh overlay, modern clean aesthetic"
        ),
        "default_subject": (
            "soft circular light bloom at center, subtle floating particles"
        ),
        "tech_specs": (
            "8K resolution, professional color grading, "
            "modern minimalist poster design, "
            "Xiaohongshu cover optimized, clean legible composition"
        ),
    },
}


# =========================================================
# 老字典兼容 — 仍可被老代码引用
# =========================================================

KNOWLEDGE_STYLES = {
    k: v for k, v in STYLE_LIBRARY.items()
    if v.get("vertical") in ("knowledge", "universal")
}
HEALING_STYLES = {
    k: v for k, v in STYLE_LIBRARY.items()
    if v.get("vertical") in ("healing", "universal")
}
STYLE_REGISTRY = {
    "knowledge": KNOWLEDGE_STYLES,
    "healing": HEALING_STYLES,
}


# =========================================================
# 核心: 3 层 Prompt 合成
# =========================================================

def build_image_prompt(
    vertical: str,           # 'knowledge' | 'healing'
    style_key: str,          # 用户在 UI 选的风格 key
    topic: str = "",         # 选题(用于匹配 subject)
    mood: str = "",          # healing 才有,knowledge 留空
    user_detail: str = "",   # 用户额外画面细节(选填)
) -> dict:
    """
    三层 Prompt 合成:
        Layer 1: Style  (固定,来自 STYLE_LIBRARY)
        Layer 2: Semantic (动态,来自 subject_library 匹配)
        Layer 3: Emotion (动态,来自 emotion_lexicon)
    """

    # ---- Layer 1: Style ----
    style = STYLE_LIBRARY.get(style_key)
    if not style:
        # fallback: 按垂类取第一个
        styles = STYLE_REGISTRY.get(vertical, KNOWLEDGE_STYLES)
        style_key = next(iter(styles))
        style = styles[style_key]

    # ---- Layer 2: Semantic ----
    subject_group = match_subject(topic, vertical) if topic else None
    if subject_group:
        subject_prompt = random.choice(subject_group["subjects"])
        negative_subject = subject_group.get("negative_subjects", [""])[0]
    else:
        subject_prompt = style.get("default_subject", "")
        negative_subject = ""

    # ---- Layer 3: Emotion ----
    if vertical == "healing" and mood:
        emotion_key = MOOD_TO_EMOTION.get(mood, "治愈温柔")
    else:
        emotion_key = "专业理性"
    emotion = EMOTION_LEXICON[emotion_key]

    emotion_prompt = (
        f"{emotion['color_palette']}, "
        f"{emotion['light_direction']}, "
        f"{emotion['composition']}, "
        f"{emotion['atmosphere']}"
    )

    # ---- 用户细节 ----
    detail_part = f", {user_detail}" if user_detail else ""

    # ---- 合成最终 Prompt ----
    final = (
        f"{style['base']}, "
        f"{subject_prompt}, "
        f"{emotion_prompt}"
        f"{detail_part}, "
        f"{style['tech_specs']}"
    )

    # ---- 合成 Negative Prompt ----
    negative_parts = [GLOBAL_NEGATIVE]
    if negative_subject:
        negative_parts.append(negative_subject)
    neg_emotion = emotion.get("negative_emotion", "")
    if neg_emotion:
        negative_parts.append(neg_emotion)
    negative = ", ".join(negative_parts)

    return {
        "vertical": vertical,
        "style_key": style_key,
        "style_label": style["label"],
        "emotion_key": emotion_key,
        "prompt": final,
        "negative": negative,
    }


# =========================================================
# Art Director LLM 菜单
# =========================================================

def list_style_keys(vertical: str) -> list:
    """列出某垂类所有可用 style_key"""
    styles = STYLE_REGISTRY.get(vertical, KNOWLEDGE_STYLES)
    return list(styles.keys())


def get_styles_guide_for_llm(vertical: str) -> str:
    """生成给 Art Director LLM 看的风格菜单"""
    styles = STYLE_REGISTRY.get(vertical, KNOWLEDGE_STYLES)
    vname = "知识博主" if vertical == "knowledge" else "治愈语录"
    lines = [f"【{vname}】可选图像风格："]
    for key, conf in styles.items():
        lines.append(f"  · {key}: {conf['label']} — {conf['base'][:80]}...")
    return "\n".join(lines)


# ---- 老接口兼容 ----
def classify_topic(topic: str) -> str:
    from verticals import auto_detect_vertical
    return auto_detect_vertical(topic)


def get_prompt_guide_for_llm() -> str:
    return (
        get_styles_guide_for_llm("knowledge") + "\n\n" +
        get_styles_guide_for_llm("healing")
    )
