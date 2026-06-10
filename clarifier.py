"""
=============================================================
小红书 AI Studio - Clarifier 选题深化引擎 (v2.0)
=============================================================
用户输入"考研分享"这种模糊选题时,Agent 应该追问到
"3 个月二战 408 计算机考研给在职党的复习节奏" 这种可执行的具体选题。

混合式交互(快 + 智能):
    Step 1 ┃ 用户输入原始选题
    Step 2 ┃ 自动识别垂类(或用户手选)
    Step 3 ┃ 展示 3 个垂类专属的框架问题(表单,30 秒填完)
    Step 4 ┃ LLM 基于答案生成 1 个个性化追问(挖反差/痛点/细节)
    Step 5 ┃ 用户答完追问 → 组装结构化简报 → 交给 Trend Analyst

状态在 Streamlit session_state 中保存,跨 rerun 持久化。
=============================================================
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from config import config
from verticals import (
    VERTICALS, get_vertical, auto_detect_vertical, get_clarify_questions
)


# =========================================================
#  Clarifier 状态机
# =========================================================

@dataclass
class ClarifierState:
    """
    Clarifier 的会话状态,完整描述用户在追问环节走到了哪一步

    stage 状态机:
        initial         → 用户刚输入原始选题
        framework       → 等用户填 3 个框架问题
        style_mood      → 选 style + (healing 专属) mood
        llm_followup    → LLM 已生成追问,等用户回答
        ready           → 全部信息齐备,可移交 Trend Analyst
    """
    stage: str = "initial"
    raw_topic: str = ""
    vertical: str = ""                          # "knowledge" | "healing"
    vertical_auto_detected: bool = False        # 是否自动识别(给 UI 提示)
    framework_answers: Dict[str, str] = field(default_factory=dict)
    # ---- v2.1 3-layer prompt fields ----
    style_key: str = ""                         # 用户选的风格 key
    mood: str = ""                              # healing 专属情绪标签
    user_detail: str = ""                       # 用户额外画面细节
    llm_followup_question: str = ""
    llm_followup_answer: str = ""
    final_brief: str = ""                        # 最终的结构化选题简报

    def to_dict(self) -> dict:
        return asdict(self)


# =========================================================
#  核心方法
# =========================================================

def kick_off(raw_topic: str, user_vertical: Optional[str] = None) -> ClarifierState:
    """
    用户首次提交原始选题时调用
    -----------------------------------
    · raw_topic: 用户输入的原始选题
    · user_vertical: 用户手选的垂类(可空,空则自动识别)

    返回填好 vertical 后的 state,stage = 'framework'
    """
    state = ClarifierState(raw_topic=raw_topic.strip())

    if user_vertical and user_vertical in VERTICALS:
        state.vertical = user_vertical
        state.vertical_auto_detected = False
    else:
        detected = auto_detect_vertical(raw_topic)
        if detected == "unknown":
            # 兜底默认 knowledge(可让用户切换)
            state.vertical = "knowledge"
            state.vertical_auto_detected = False
        else:
            state.vertical = detected
            state.vertical_auto_detected = True

    state.stage = "framework"
    return state


def submit_framework(state: ClarifierState, answers: Dict[str, str]) -> ClarifierState:
    """
    用户填完 3 个框架问题后调用
    -----------------------------------
    · answers: {'subject': '...', 'stage': '...', 'audience': '...'}

    会触发 LLM 生成个性化追问,把结果填进 state.llm_followup_question
    stage 推进到 'llm_followup'
    """
    state.framework_answers = answers

    try:
        state.llm_followup_question = _generate_followup(
            vertical=state.vertical,
            raw_topic=state.raw_topic,
            framework_answers=answers,
        )
    except Exception as e:
        print(f"[Clarifier] LLM 追问生成失败,跳过该步骤: {e}")
        state.llm_followup_question = ""  # 跳过追问

    if state.llm_followup_question:
        state.stage = "llm_followup"
    else:
        # 追问生成失败,直接进入 ready
        state.final_brief = _assemble_brief(state)
        state.stage = "ready"
    return state


def submit_followup(state: ClarifierState, answer: str) -> ClarifierState:
    """
    用户回答完 LLM 追问后调用 → 进入 ready 状态
    """
    state.llm_followup_answer = answer.strip()
    state.final_brief = _assemble_brief(state)
    state.stage = "ready"
    return state


def skip_followup(state: ClarifierState) -> ClarifierState:
    """用户主动跳过 LLM 追问"""
    state.llm_followup_answer = ""
    state.final_brief = _assemble_brief(state)
    state.stage = "ready"
    return state


def switch_vertical(state: ClarifierState, new_vertical: str) -> ClarifierState:
    """用户手动切换垂类,重置到 framework 步骤"""
    state.vertical = new_vertical
    state.vertical_auto_detected = False
    state.framework_answers = {}
    state.llm_followup_question = ""
    state.llm_followup_answer = ""
    state.final_brief = ""
    state.stage = "framework"
    return state


# =========================================================
#  内部:LLM 个性化追问生成
# =========================================================

def _generate_followup(
    vertical: str,
    raw_topic: str,
    framework_answers: Dict[str, str],
) -> str:
    """
    调用 LLM 生成 1 个高质量的个性化追问
    用 deepseek-chat 即可(短任务,便宜稳定)
    """
    vconf = get_vertical(vertical)
    framework_str = "\n".join(
        f"  · {q['label']}: {framework_answers.get(q['key'], '(未填)')}"
        for q in vconf["clarify_framework"]
    )

    system_prompt = (
        "你是一位资深的小红书内容选题深化师。"
        "用户给了你一个粗略的选题方向,你的工作是问出 1 个最关键的追问,"
        "帮他把选题挖到具体到可以直接写文案的程度。\n\n"
        f"当前垂类:{vconf['name']}({vconf['description']})\n\n"
        f"{vconf['llm_followup_guide']}\n\n"
        "硬性要求:\n"
        "  1. 只问 1 个问题,不要列举多个\n"
        "  2. 问题要具体,带 2-3 个示例选项作为参考(用括号给出)\n"
        "  3. 控制在 60 字以内\n"
        "  4. 直接输出问题本身,不要任何前缀或说明"
    )

    user_msg = (
        f"用户原始选题: {raw_topic}\n\n"
        f"用户填的框架信息:\n{framework_str}\n\n"
        f"请生成 1 个最关键的追问。"
    )

    # 直接走 OpenAI 兼容客户端(短任务不用 CrewAI LLM 包装)
    from openai import OpenAI
    client = OpenAI(
        api_key=config.deepseek_api_key,
        base_url=config.deepseek_base_url,
        timeout=20,
    )
    resp = client.chat.completions.create(
        model=config.deepseek_chat_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.6,
        max_tokens=120,
    )
    question = resp.choices[0].message.content.strip()
    # 简单清洗(去掉可能的引号/前缀)
    for prefix in ["追问:", "问题:", "Q:", "："]:
        if question.startswith(prefix):
            question = question[len(prefix):].strip()
    return question.strip('"\'""')


# =========================================================
#  内部:组装最终选题简报
# =========================================================

def _assemble_brief(state: ClarifierState) -> str:
    """
    把所有问答信息汇总成一份结构化简报
    这份简报会作为"增强版 topic"传给 Trend Analyst,
    取代原始的简短选题词
    """
    vconf = get_vertical(state.vertical)
    lines = [
        f"## 📋 选题简报",
        f"**垂类**: {vconf['name']} {vconf['icon']}",
        f"**原始选题**: {state.raw_topic}",
        f"",
        f"### 框架信息",
    ]
    for q in vconf["clarify_framework"]:
        ans = state.framework_answers.get(q["key"], "")
        if ans:
            lines.append(f"- **{q['label']}**: {ans}")

    if state.style_key:
        lines.append(f"- **图像风格**: {state.style_key}")
    if state.mood:
        lines.append(f"- **情绪基调**: {state.mood}")
    if state.user_detail:
        lines.append(f"- **画面细节**: {state.user_detail}")

    if state.llm_followup_question:
        lines.append(f"\n### 个性化细节")
        lines.append(f"- **追问**: {state.llm_followup_question}")
        if state.llm_followup_answer:
            lines.append(f"- **用户回答**: {state.llm_followup_answer}")
        else:
            lines.append(f"- **用户回答**: (用户跳过)")

    return "\n".join(lines)


# =========================================================
#  辅助:从简报中提取一个简洁的 topic 字符串(供日志显示)
# =========================================================

def state_to_short_topic(state: ClarifierState) -> str:
    """把 state 凝练成一句话,用于日志/进度展示"""
    parts = [state.raw_topic]
    if state.framework_answers.get("subject"):
        parts.append(state.framework_answers["subject"])
    if state.framework_answers.get("stage"):
        parts.append(state.framework_answers["stage"].split("(")[0])
    if state.framework_answers.get("audience"):
        parts.append(state.framework_answers["audience"].split("(")[0])
    if state.llm_followup_answer:
        parts.append(state.llm_followup_answer[:30])
    return " · ".join(parts)
