EMOTION_LEXICON = {
    # 治愈温柔
    "治愈温柔": {
        "color_palette": "warm amber, soft peach, cream, dusty pink",
        "light_direction": "golden hour sidelight, soft diffused",
        "composition": "centered, balanced, gentle curves",
        "atmosphere": "embracing, gentle, comforting, slow",
        "negative_emotion": "no harsh shadows, no cold tones",
    },

    # 释怀洒脱
    "释怀洒脱": {
        "color_palette": "open sky blues, soft gold, pale lavender, white",
        "light_direction": "wide overhead light, expansive",
        "composition": "horizon line, abundant negative space, "
                       "subject in lower third",
        "atmosphere": "open, liberated, breathing, vast",
        "negative_emotion": "no enclosed spaces, no dark heavy tones",
    },

    # 深夜共鸣 / 孤独
    "深夜共鸣": {
        "color_palette": "deep indigo, midnight blue, warm yellow accent, "
                         "muted teal",
        "light_direction": "single point warm light, surrounded by darkness",
        "composition": "isolated subject, lots of dark negative space, "
                       "intimate close framing",
        "atmosphere": "quiet, contemplative, lonely but tender",
        "negative_emotion": "no bright sun, no crowds, no warm yellow dominant",
    },

    # 毒鸡汤 / 清醒扎心
    "毒鸡汤": {
        "color_palette": "monochrome with single accent color, "
                         "high contrast, cool grays",
        "light_direction": "sharp directional, dramatic shadows",
        "composition": "asymmetric, bold, stark",
        "atmosphere": "stark, clear, unflinching, modern",
        "negative_emotion": "no soft pastels, no overly warm tones",
    },

    # 勇气希望
    "勇气希望": {
        "color_palette": "sunrise orange, warm pink, hopeful yellow, "
                         "soft white",
        "light_direction": "low angle uplighting, sunrise direction",
        "composition": "ascending lines, subject reaching upward, "
                       "rule of thirds with subject lower",
        "atmosphere": "uplifting, gentle hope, new beginning, soft strength",
        "negative_emotion": "no descending lines, no sunset tones, "
                            "no dark heavy mood",
    },

    # knowledge 默认(不强调情绪,只要专业感)
    "专业理性": {
        "color_palette": "warm neutral, cream, soft sage, muted blue",
        "light_direction": "natural even daylight",
        "composition": "balanced, organized, geometric",
        "atmosphere": "focused, calm, productive, clean",
        "negative_emotion": "no dramatic mood",
    },
}
# verticals.py 里 healing 的 mood 选项已经是:
# "治愈温柔(给疲惫的人一点光)"
# "释怀洒脱(放过自己/向前看)"  
# "毒鸡汤(扎心但清醒的真相)"
# "深夜共鸣(写给同样睡不着的人)"
# "勇气与希望(给迷茫的人打气)"

MOOD_TO_EMOTION = {
    "治愈温柔": "治愈温柔",
    "释怀洒脱": "释怀洒脱",
    "毒鸡汤":   "毒鸡汤",
    "深夜共鸣": "深夜共鸣",
    "勇气":     "勇气希望",
}