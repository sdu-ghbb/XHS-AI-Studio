"""
=============================================================
小红书 AI Studio - 角色与任务编排 (v1.3 / Sprint 1-3)
=============================================================
本版变更：
  · Copywriter 装配 ComplianceCheck Skill（产出后自查违禁词）
  · Art Director 升级：模板选择 + 可选组图
  · 新增 run_crew_with_retry：Critic 评分 <阈值 自动带建议重跑
  · prompt 模板库注入 Art Director
=============================================================
"""

import re
from typing import Callable, Optional, Tuple
from crewai import Agent, Task, Crew, Process, LLM

from config import config
from tools import (
    BochaSearchTool, SmartImagePosterTool,
    VLMCritiqueTool, ComplianceCheckTool, ShadowKBTool,
)
from examples import FEWSHOT_EXAMPLES, EMOJI_RULES, HOT_HOOK_WORDS
from templates import list_templates_for_llm
from prompts import build_image_prompt, get_prompt_guide_for_llm


# =========================================================
#  LLM 工厂
# =========================================================

def build_llm(provider: str, temperature: float = 0.7) -> LLM:
    """统一 LLM 构造入口"""
    provider = provider.lower().strip()

    if provider == "deepseek":
        return LLM(model=f"deepseek/{config.deepseek_chat_model}",
                   api_key=config.deepseek_api_key, temperature=temperature)
    elif provider == "deepseek-reasoner":
        return LLM(model=f"deepseek/{config.deepseek_reasoner_model}",
                   api_key=config.deepseek_api_key, temperature=temperature)
    elif provider == "doubao":
        return LLM(model=f"openai/{config.doubao_pro_model}",
                   api_key=config.doubao_api_key,
                   base_url=config.doubao_base_url, temperature=temperature)
    elif provider == "doubao-lite":
        return LLM(model=f"openai/{config.doubao_lite_model}",
                   api_key=config.doubao_api_key,
                   base_url=config.doubao_base_url, temperature=temperature)
    elif provider == "qianwen":
        return LLM(model=f"openai/{config.qianwen_max_model}",
                   api_key=config.qianwen_api_key,
                   base_url=config.qianwen_base_url, temperature=temperature)
    elif provider == "qianwen-plus":
        return LLM(model=f"openai/{config.qianwen_plus_model}",
                   api_key=config.qianwen_api_key,
                   base_url=config.qianwen_base_url, temperature=temperature)
    else:
        raise ValueError(f"未知 provider: {provider}")


# =========================================================
#  Crew 组装
# =========================================================

def build_crew(
    topic: str,
    step_callback: Optional[Callable] = None,
    output_dir: str = "./outputs",
    retry_feedback: Optional[str] = None,
    enable_carousel: bool = False,
):
    """
    组建 4-Agent Crew

    Parameters
    ----------
    topic : str            选题关键词
    step_callback          实时日志回调
    output_dir             海报输出目录
    retry_feedback : str   若非空，作为改进意见注入 Copywriter（自检重跑用）
    enable_carousel : bool 是否生成组图（封面 + 正文图）
    """

    # ----- LLM -----
    trend_llm = build_llm(config.trend_analyst_provider, temperature=0.3)
    copy_llm = build_llm(config.copywriter_provider, temperature=0.85)
    art_llm = build_llm(config.art_director_provider, temperature=0.5)
    critic_llm = build_llm(config.critic_provider, temperature=0.2)

    # ----- Skill -----
    kb_skill = ShadowKBTool()
    search_skill = BochaSearchTool()
    poster_skill = SmartImagePosterTool(output_dir=output_dir)
    vlm_skill = VLMCritiqueTool()
    compliance_skill = ComplianceCheckTool()

    # ----- 选题预分析 -----
    prompt_info = build_image_prompt(topic)
    suggested_template = prompt_info["recommended_template"]
    topic_category = prompt_info["category"]

    # ============ Agent 1: 趋势分析师 ============
    trend_analyst = Agent(
        role="爆款趋势分析师",
        goal=(
            f"针对选题 '{topic}'，优先从影子题库检索真实爆款笔记，"
            f"辅以网络爆款拆解文章，提炼用户痛点、爆款标题套路、热门话题标签，"
            f"输出结构化选题策略报告。"
        ),
        backstory=(
            "你是深耕新媒体 8 年的内容策略专家，操盘过数十个百万爆款。\n"
            "你的工作方法是『双数据源』：\n"
            "  1. 影子题库（ShadowKBSearch）—— 本地维护的真实历史爆款库，"
            "     这是你最信任的语料，因为它 100% 是纯正小红书内容；\n"
            "  2. 网络拆解文章（BochaWebSearch）—— 公众号/知乎上 MCN 机构"
            "     和操盘手写的爆款拆解报告，帮你站在别人的分析肩膀上。\n"
            "你总是先查影子题库打底，再用网络搜索补充最新趋势。"
            "输出永远结构化、不冗余。"
        ),
        tools=[kb_skill, search_skill],
        llm=trend_llm, verbose=True, allow_delegation=False,
        step_callback=step_callback, max_iter=6,
    )

    # ============ Agent 2: 金牌文案（Few-shot + 合规）============
    hot_words_str = "、".join(HOT_HOOK_WORDS[:18])
    copywriter = Agent(
        role="新媒体金牌文案",
        goal=(
            "基于策略报告撰写地道的小红书爆款图文，"
            "用 ComplianceCheck 工具自查违禁词并修正，"
            "最后提炼 ≤15 字的核心海报标题。"
        ),
        backstory=(
            "你是小红书 50w+ 粉丝头部博主背后的金牌文案，"
            "写作风格直接模仿以下 5 篇真实爆款笔记（学习钩子、emoji 节奏、"
            "分段方式、用词，禁止露出 AI 痕迹）：\n\n"
            "════════ 爆款样本库 ════════\n"
            f"{FEWSHOT_EXAMPLES}\n"
            "════════════════════════════\n\n"
            f"高频钩子词（每篇至少用 3 个）：{hot_words_str}\n\n"
            f"{EMOJI_RULES}\n\n"
            "你还非常注重合规——深知违禁词会让笔记限流甚至封号，"
            "所以写完一定会用 ComplianceCheck 工具自查。"
        ),
        tools=[compliance_skill],
        llm=copy_llm, verbose=True, allow_delegation=False,
        step_callback=step_callback, max_iter=4,
    )

    # ============ Agent 3: 视觉总监（模板 + 组图）============
    art_director = Agent(
        role="视觉排版总监",
        goal=(
            "根据文案立意撰写英文图像 Prompt，选择最合适的海报模板，"
            "调用 ImagePoster 工具完成生图 + 叠字。"
        ),
        backstory=(
            "你是 4A 出身的视觉总监，深谙小红书封面美学。\n"
            f"{list_templates_for_llm()}\n\n"
            f"{get_prompt_guide_for_llm()}\n\n"
            "你写的 prompt 永远包含负向词避免底图自带文字。"
        ),
        tools=[poster_skill],
        llm=art_llm, verbose=True, allow_delegation=False,
        step_callback=step_callback, max_iter=4,
    )

    # ============ Agent 4: 质量审核总监 ============
    critic = Agent(
        role="爆款质量审核总监",
        goal=(
            "审核文案和海报，从爆款潜力/小红书味/视觉吸引力三维度严格打分，"
            "输出可执行的改进建议。"
        ),
        backstory=(
            "你是头部 MCN 机构的内容质量总监，过手爆款超 500 篇。"
            "你打分苛刻——80 分以上才有爆款潜力。"
            "你的建议永远具体到可执行，不说'要更吸引人'这种废话。"
        ),
        tools=[vlm_skill],
        llm=critic_llm, verbose=True, allow_delegation=False,
        step_callback=step_callback, max_iter=3,
    )

    # ============ Task 1: 选题策略 ============
    task_trend = Task(
        description=(
            f"针对用户选题【{topic}】（已归类为「{topic_category}」品类）：\n"
            f"1. 【第一步·必做】用 ShadowKBSearch 工具检索影子题库，"
            f"   query 传 '{topic}'，category 传 '{topic_category}'（若该品类"
            f"   不在题库分类中则 category 留空）。这会返回真实历史爆款笔记；\n"
            f"2. 【第二步·补充】用 BochaWebSearch 检索 1-2 次最新爆款拆解文章"
            f"   （如 '{topic} 痛点' / '{topic} 标题套路'），"
            f"   工具会自动进阶为'爆款拆解'搜索；\n"
            f"   ⚠️ 若 ShadowKBSearch 返回'题库未构建'，则把 Bocha 作为主数据源；\n"
            f"3. 综合两个数据源，总结目标人群 3-5 个核心痛点"
            f"   （优先引用影子题库里真实笔记体现的痛点）；\n"
            f"4. 提炼 3 套验证过的爆款标题套路，每套配 1 个套用该选题的示范标题；\n"
            f"5. 给出 5 个相关热门话题标签（#xxx）。\n"
            f"全程中文，结构化 Markdown。"
        ),
        expected_output=(
            "Markdown 报告：### 数据来源说明（用了题库还是网络）/ "
            "### 用户痛点 / ### 爆款标题套路 / ### 热门话题标签"
        ),
        agent=trend_analyst,
    )

    # ============ Task 2: 文案撰写 ============
    retry_block = ""
    if retry_feedback:
        retry_block = (
            f"\n\n⚠️⚠️ 这是重写任务！上一版文案质量未达标。\n"
            f"质检员的改进意见如下，请务必针对性改进：\n"
            f"-------------------\n{retry_feedback}\n-------------------\n"
        )

    task_copy = Task(
        description=(
            "基于策略报告撰写小红书爆款图文：\n"
            "1. 文章标题（≤20 字，带钩子，参考样本库风格）；\n"
            "2. 正文 300-500 字，分 3-5 个干货段落，每段开头 1 个 emoji；\n"
            "3. 文末 5 个 # 话题标签；\n"
            "4. ⚠️ 写完后【必须】调用 ComplianceCheck 工具检查全文，"
            "   如有违禁词，按建议改写后再输出；\n"
            "5. 末尾【严格固定格式】依次输出两行锚点：\n"
            "   `海报标题: xxx`   (xxx ≤15 汉字，口语化，有冲击力，不含 emoji)\n"
            "   `分页标题: A | B | C`   (3 个干货段落的精简小标题，每个 ≤8 字，"
            "    用 ` | ` 分隔；若内容不适合组图可写 `分页标题: 无`)\n\n"
            "⚠️ 硬性要求：至少用 3 个钩子词；emoji 只放标题尾和段首；"
            "全文 emoji ≤8 个；禁止 'AI 八股'（让我们/综上所述/总而言之）。"
            + retry_block
        ),
        expected_output=(
            "完整图文 + `海报标题: xxx` + `分页标题: ...` 两行锚点"
        ),
        agent=copywriter,
        context=[task_trend],
    )

    # ============ Task 3: 视觉合成 ============
    carousel_instr = (
        (
            "5. 【组图模式已开启】从文案的 `分页标题: A | B | C` 锚点提取分页标题，"
            "   作为 sub_headlines 参数传入（原样保留 ` | ` 分隔）。"
            "   若锚点是 `分页标题: 无` 则 sub_headlines 留空。\n"
        )
        if enable_carousel else
        "5. 【单图模式】sub_headlines 参数留空。\n"
    )

    task_visual = Task(
        description=(
            "基于文案主题执行视觉合成：\n"
            "1. 从文案 `海报标题: xxx` 锚点提取 xxx 作为 headline；\n"
            "2. 撰写【英文】图像 Prompt（风格关键词丰富，真人场景加 "
            "'natural skin texture'，**必须**含 'no text, no letters'）；\n"
            f"3. 选择海报模板：本选题品类推荐 `{suggested_template}`，"
            "   你可根据文案调性最终决定（4 选 1）；\n"
            "4. 如模板是 top_label 或 magazine_cover，再拟一个 ≤6 字的 subtitle；\n"
            + carousel_instr +
            "6. 调用 ImagePoster 工具（参数：prompt / headline / template / "
            "subtitle / sub_headlines）；\n"
            "7. 返回工具给出的全部路径 + 30 字内视觉说明。"
        ),
        expected_output="海报路径（可能多张）+ 视觉说明",
        agent=art_director,
        context=[task_copy],
    )

    # ============ Task 4: 质量审核 ============
    task_critique = Task(
        description=(
            "审核前三个 Agent 的产出：\n\n"
            "## 1. 文案审核（0-100）\n"
            "  标题钩子(0-25) / 风格地道(0-25) / 干货密度(0-25) / 话题标签(0-25)\n\n"
            "## 2. 海报审核（必须调用 VLMCritique，传 "
            "image_path='./outputs/poster_final.jpg'，0-100）\n\n"
            "## 3. 严格按以下格式输出：\n"
            "```\n"
            "## 📊 质量审核报告\n\n"
            "### 文案评分\n"
            "- 标题钩子: X/25 — 原因\n"
            "- 风格地道: X/25 — 原因\n"
            "- 干货密度: X/25 — 原因\n"
            "- 话题标签: X/25 — 原因\n"
            "- **文案总分: X/100**\n\n"
            "### 海报评分（来自 VLM）\n"
            "[附 VLM 工具返回原文]\n"
            "- **海报总分: X/100**\n\n"
            "### 综合判定\n"
            "- **综合评分: X/100** (文案 50% + 海报 50%)\n"
            "- 等级: 🟢爆款潜力 / 🟡合格 / 🔴需改进\n\n"
            "### 🛠 改进建议\n"
            "1. [文案具体建议]\n"
            "2. [海报具体建议]\n"
            "```"
        ),
        expected_output="按格式的完整质量审核 Markdown 报告",
        agent=critic,
        context=[task_copy, task_visual],
    )

    crew = Crew(
        agents=[trend_analyst, copywriter, art_director, critic],
        tasks=[task_trend, task_copy, task_visual, task_critique],
        process=Process.sequential,
        verbose=True,
    )
    return crew, [task_trend, task_copy, task_visual, task_critique]


# =========================================================
#  自检循环：Critic 评分 < 阈值则带建议重跑
# =========================================================

def parse_total_score(critic_text: str) -> Optional[int]:
    """从 Critic 输出中提取综合评分"""
    if not critic_text:
        return None
    m = re.search(r"综合评分[:：]\s*\**\s*(\d+)\s*/\s*100", critic_text)
    return int(m.group(1)) if m else None


def extract_suggestions(critic_text: str) -> str:
    """从 Critic 输出中提取'改进建议'章节"""
    if not critic_text:
        return ""
    m = re.search(r"改进建议\s*\n(.+?)(?:```|$)", critic_text, re.DOTALL)
    return m.group(1).strip() if m else critic_text[-500:]


def run_crew_with_retry(
    topic: str,
    step_callback: Optional[Callable] = None,
    output_dir: str = "./outputs",
    enable_carousel: bool = False,
    max_attempts: int = 2,
    log_fn: Optional[Callable] = None,
) -> Tuple[object, list, int]:
    """
    带自检循环的 Crew 执行入口
    -----------------------------------
    第一次正常跑完 4 个 Agent；
    若 Critic 综合评分 < config.quality_threshold，
    把改进建议注入 Copywriter，重跑（最多 max_attempts 次）。

    Returns
    -------
    (last_result, last_tasks, final_score)
    """
    def _log(msg, typ="info"):
        if log_fn:
            log_fn(msg, typ)

    feedback = None
    last_result, last_tasks, last_score = None, None, 0

    for attempt in range(1, max_attempts + 1):
        if attempt == 1:
            _log(f"🚀 第 {attempt} 轮：四 Agent 协作开始")
        else:
            _log(f"🔁 第 {attempt} 轮：上轮分数 {last_score} 未达标"
                 f"（阈值 {config.quality_threshold}），带建议重跑文案")

        crew, tasks = build_crew(
            topic=topic,
            step_callback=step_callback,
            output_dir=output_dir,
            retry_feedback=feedback,
            enable_carousel=enable_carousel,
        )
        result = crew.kickoff()

        critic_out = ""
        try:
            out = tasks[3].output
            critic_out = (getattr(out, "raw", None)
                          or getattr(out, "raw_output", None)
                          or str(out))
        except Exception:
            pass

        score = parse_total_score(critic_out) or 0
        last_result, last_tasks, last_score = result, tasks, score

        if score >= config.quality_threshold:
            _log(f"✅ 第 {attempt} 轮综合评分 {score}，达标，停止迭代", "done")
            break
        elif attempt < max_attempts:
            feedback = extract_suggestions(critic_out)
            _log(f"⚠️ 第 {attempt} 轮评分 {score}，准备重跑", "info")
        else:
            _log(f"⚠️ 已达最大重试次数，最终评分 {last_score}", "info")

    return last_result, last_tasks, last_score
