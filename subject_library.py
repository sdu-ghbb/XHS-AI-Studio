SUBJECT_LIBRARY = {
    # knowledge 子类
    "考研考公": {
        "match_keywords": ["考研", "考公", "上岸", "408", "复试", "申论", "行测"],
        "subjects": [
            # 多个备选,生图时随机选一个增加多样性
            "scattered handwritten notes with formulas and mind maps, "
            "thick textbooks stacked, red pen markings, sticky tabs, "
            "study lamp casting warm pool of light",

            "open notebook with detailed Chinese handwriting, "
            "highlighted key concepts, ruler and pencils, "
            "thermos and a clock showing late hours",
        ],
        "negative_subjects": [
            "no specific university logos, no specific exam papers"
        ],
    },

    "AI编程": {
        "match_keywords": ["AI工具", "Python", "ChatGPT", "Midjourney", "编程", "代码"],
        "subjects": [
            "modern minimalist workspace with glowing screens, "
            "abstract neural network patterns floating above, "
            "blue and purple gradient ambient light, "
            "futuristic but warm atmosphere",

            "clean desk with multiple monitors showing abstract code, "
            "soft RGB ambient lighting, mechanical keyboard, "
            "modern tech aesthetic, no specific software interfaces",
        ],
    },

    "副业搞钱": {
        "match_keywords": ["副业", "搞钱", "赚钱", "自媒体", "接单"],
        "subjects": [
            "minimalist desk with laptop, notebook with sketched ideas, "
            "succulent plants, coffee mug, golden hour window light, "
            "feeling of focused independent work, no specific brands",
        ],
    },

    "职场技能": {
        "match_keywords": ["职场", "PPT", "Excel", "面试", "升职", "汇报"],
        "subjects": [
            "elegant office desk flatlay, leather notebook, fountain pen, "
            "subtle business aesthetics, neutral tones, professional"
        ],
    },

    "读书认知": {
        "match_keywords": ["读书", "书单", "认知", "思维"],
        "subjects": [
            "stack of vintage books with bookmark, warm reading lamp, "
            "cozy library corner, dust particles in light beam, "
            "old paper texture, intellectual cozy atmosphere"
        ],
    },

    "英语学习": {
        "match_keywords": ["英语", "雅思", "托福", "六级", "口语"],
        "subjects": [
            "open english dictionary with handwritten notes, vintage globe, "
            "warm lamp light, classic study aesthetic, paper texture"
        ],
    },

    "学习方法": {
        "match_keywords": ["学习方法", "时间管理", "自律", "效率"],
        "subjects": [
            "structured study schedule on paper, geometric arrangement, "
            "morning sunlight, clean composition with negative space, "
            "minimal modern aesthetic"
        ],
    },

    "工具盘点": {
        "match_keywords": ["工具", "神器", "App", "网站", "推荐"],
        "subjects": [
            "abstract grid of glowing icons floating in space, "
            "modern flat illustration, soft gradient background, "
            "minimal geometric composition"
        ],
    },

    # ============ healing 子类 ============
    "晚安心语": {
        "match_keywords": ["晚安", "深夜", "失眠", "睡前"],
        "subjects": [
            "lonely window view at midnight, soft moonlight streaming in, "
            "single lamp casting warm pool of light, empty room corner, "
            "feeling of quiet solitude",
        ],
    },

    "辞职职场": {
        "match_keywords": ["辞职", "裸辞", "离职", "Gap", "内耗"],
        "subjects": [
            "empty office chair turned away, scattered papers settling, "
            "warm afternoon light through blinds, sense of leaving behind, "
            "open window with curtain blowing"
        ],
    },

    "北漂打工": {
        "match_keywords": ["北漂", "沪漂", "深漂", "打工人", "通勤", "出租屋"],
        "subjects": [
            "distant city skyline at dusk, blurred lights of skyscrapers, "
            "rain-streaked window in foreground, "
            "loneliness of urban life, no specific landmarks",

            "lone silhouette walking down empty subway platform, "
            "fluorescent lights, late night urban solitude, "
            "wide composition emphasizing scale"
        ],
    },

    "自我接纳": {
        "match_keywords": ["和解", "接纳", "自洽", "成长", "26岁", "30岁"],
        "subjects": [
            "open hands releasing dandelion seeds, soft backlit golden hour, "
            "wide sky with gentle clouds, sense of letting go and embrace, "
            "minimal painterly composition",

            "single small plant growing through stone, soft morning light, "
            "metaphor of quiet strength, shallow depth of field"
        ],
    },

    "释怀放下": {
        "match_keywords": ["释怀", "放下", "戒掉", "走出"],
        "subjects": [
            "wide ocean horizon at dawn, single bird flying away, "
            "vast empty sky, feeling of release and openness, "
            "minimal composition with abundant negative space"
        ],
    },

    "孤独独处": {
        "match_keywords": ["一个人", "独居", "独处", "单身"],
        "subjects": [
            "steaming coffee cup by window, soft morning light, "
            "quiet peaceful solo moment, warm but solitary atmosphere"
        ],
    },
}
def match_subject(topic: str, vertical: str) -> dict:
    """从选题里匹配最合适的 subject group"""
    scores = {}
    for cat_key, conf in SUBJECT_LIBRARY.items():
        score = sum(1 for kw in conf["match_keywords"] if kw in topic)
        if score > 0:
            scores[cat_key] = score
    if not scores:
        return None
    best = max(scores, key=scores.get)
    return SUBJECT_LIBRARY[best]