"""
=============================================================
小红书 AI Studio - 垂类配置中枢 (v2.0 双垂类聚焦)
=============================================================
本应用聚焦两个 AI 生图友好的垂类：
    📚 knowledge —— 知识博主(学习/考试/职场/技能/副业/读书笔记)
    🌙 healing   —— 治愈语录(情感/共鸣/星座/治愈/毒鸡汤/辞职文学)

每个垂类配置：
    · 关键词(自动识别用)
    · Clarifier 追问框架(3 个核心结构化问题)
    · 推荐海报模板
    · Critic 评分权重(各垂类侧重不同)
=============================================================
"""

from typing import Dict, List


VERTICALS: Dict[str, Dict] = {

    # ============================================================
    # 📚 知识博主
    # ============================================================
    "knowledge": {
        "name": "知识博主",
        "icon": "📚",
        "description": "学习/考试/职场/技能/副业/读书笔记类内容",

        # 自动识别关键词
        "keywords": [
            "考研", "考公", "考编", "考证", "复试", "上岸",
            "学习", "笔记", "知识", "干货", "技能", "方法",
            "职场", "副业", "搞钱", "效率", "时间管理",
            "读书", "书单", "认知", "思维",
            "Python", "AI", "工具", "PPT", "Excel",
            "英语", "雅思", "考研英语", "四六级",
        ],

        # Clarifier 框架问题(3 个固定结构化问题)
        "clarify_framework": [
            {
                "key": "subject",
                "label": "具体方向/学科",
                "question": "具体是哪个细分方向?",
                "examples": ["408 计算机考研", "考公申论", "Python 数据分析",
                             "新媒体运营", "英语六级", "理财入门"],
                "required": True,
            },
            {
                "key": "stage",
                "label": "内容阶段",
                "question": "你想分享的是哪个阶段的内容?",
                "options": [
                    "入门规划(给小白的路线图)",
                    "经验复盘(过来人的踩坑总结)",
                    "干货方法(具体可执行的技巧)",
                    "工具/资源推荐",
                ],
                "required": True,
            },
            {
                "key": "audience",
                "label": "目标受众",
                "question": "主要写给谁看?",
                "options": [
                    "在校大学生",
                    "应届毕业生",
                    "在职打工人",
                    "考研/考公备考党",
                    "宝妈/转行人群",
                ],
                "required": True,
            },
        ],

        # LLM 追问的引导(给 Clarifier 看的指令)
        "llm_followup_guide": (
            "你已知用户的方向、阶段、受众。请基于这三个信息,"
            "提出 1 个最关键的追问,帮用户把选题挖得更具体。"
            "好追问应该聚焦在:具体的痛点场景 / 具体的数字成果 / 具体的反差感。"
            "例:用户说'考研经验复盘 在职考生',你可以问"
            "'你想突出的核心反差是什么?(如:在职党 vs 应届生 / 三本上岸 985 / 半年裸考)'"
        ),

        # 海报偏好
        "template": "knowledge_card",
        "template_fallback": "magazine_cover",
        "subtitle_default": "干货笔记",

        # 图像 Prompt 风格(传给 Art Director)
        "prompt_style_hint": (
            "minimalist flat illustration, abstract conceptual art, "
            "clean white background, soft pastel accent colors, "
            "academic notebook aesthetic, organized geometric shapes, "
            "no people, no realistic objects, no specific brands"
        ),

        # Critic 评分权重(总和=1.0)
        "critic_weights": {
            "hook": 0.20,        # 标题钩子
            "authenticity": 0.20, # 真实感(知识博主要可信)
            "density": 0.35,     # 干货密度(知识类核心)
            "tags": 0.10,
            "visual": 0.15,
        },
    },

    # ============================================================
    # 🌙 治愈语录
    # ============================================================
    "healing": {
        "name": "治愈语录",
        "icon": "🌙",
        "description": "情感/共鸣/治愈/毒鸡汤/辞职文学/星座/晚安心语",

        "keywords": [
            "治愈", "情感", "金句", "语录", "心语",
            "毒鸡汤", "鸡汤", "辞职", "焦虑", "孤独",
            "晚安", "深夜", "emo", "共鸣", "心情",
            "星座", "运势", "塔罗",
            "成长", "勇气", "温柔", "释怀",
            "城市", "漂泊", "独居", "一个人",
            "北漂", "沪漂", "打工人", "失眠", "想家",
            "迷茫", "委屈", "破防", "脆弱",
        ],

        "clarify_framework": [
            {
                "key": "mood",
                "label": "情绪主基调",
                "question": "你想传达的核心情绪是?",
                "options": [
                    "治愈温柔(给疲惫的人一点光)",
                    "释怀洒脱(放过自己/向前看)",
                    "毒鸡汤(扎心但清醒的真相)",
                    "深夜共鸣(写给同样睡不着的人)",
                    "勇气与希望(给迷茫的人打气)",
                ],
                "required": True,
            },
            {
                "key": "scene",
                "label": "情绪场景",
                "question": "这段文字最适合什么场景被读到?",
                "options": [
                    "深夜失眠时",
                    "通勤路上",
                    "周末独处",
                    "受了委屈/失恋后",
                    "周一上班前",
                    "节日孤独时",
                ],
                "required": True,
            },
            {
                "key": "audience",
                "label": "目标受众",
                "question": "主要写给谁看?",
                "options": [
                    "刚步入社会的大学生",
                    "北漂/沪漂打工人",
                    "在感情里疲惫的人",
                    "迷茫期的年轻人",
                    "正在治愈自己的人",
                ],
                "required": True,
            },
        ],

        "llm_followup_guide": (
            "你已知用户的情绪基调、场景、受众。请提出 1 个追问,"
            "帮用户把这段语录变得更有'画面感'。"
            "好追问应该聚焦在:具体的细节意象 / 一个想戳中的瞬间 / 一句没说出口的话。"
            "例:用户说'治愈温柔 深夜失眠 北漂打工人',你可以问"
            "'有没有一个具体瞬间想替读者说出来?(如:加班到凌晨打不到车 / "
            "想家但不敢哭 / 朋友圈三天可见后的孤独)'"
        ),

        "template": "quote_card",
        "template_fallback": "minimalist",
        "subtitle_default": "晚安心语",

        "prompt_style_hint": (
            "atmospheric cinematic landscape, golden hour soft light, "
            "dreamy bokeh, melancholic mood, painterly aesthetic, "
            "no people, no text, no buildings as main subject, "
            "evocative empty composition, muted warm tones"
        ),

        "critic_weights": {
            "hook": 0.15,
            "authenticity": 0.20,
            "density": 0.10,       # 治愈类不需要太多信息
            "tags": 0.10,
            "visual": 0.30,        # 视觉氛围更重要
            "resonance": 0.15,     # 新增维度:共鸣力
        },
    },
}


# =========================================================
#  辅助函数
# =========================================================

def list_verticals() -> List[Dict]:
    """列出所有垂类,供 UI 渲染选择按钮"""
    return [
        {"key": k, "name": v["name"], "icon": v["icon"],
         "description": v["description"]}
        for k, v in VERTICALS.items()
    ]


def auto_detect_vertical(topic: str) -> str:
    """
    根据用户输入的选题关键词自动识别垂类
    返回: 'knowledge' | 'healing' | 'unknown'
    """
    scores = {}
    for key, conf in VERTICALS.items():
        score = sum(1 for kw in conf["keywords"] if kw in topic)
        scores[key] = score

    best_key = max(scores, key=scores.get)
    if scores[best_key] == 0:
        return "unknown"
    return best_key


def get_vertical(key: str) -> Dict:
    """获取垂类配置,未知则用 knowledge 兜底"""
    return VERTICALS.get(key, VERTICALS["knowledge"])


def get_clarify_questions(vertical_key: str) -> List[Dict]:
    """获取某垂类的 Clarifier 表单问题"""
    return get_vertical(vertical_key)["clarify_framework"]
