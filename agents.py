"""
=============================================================
小红书爆款图文生成 Agent —— 角色与任务编排
=============================================================
基于 CrewAI 顺序流构建：
    [Agent 1] Trend Analyst   ── DeepSeek + WebSearch Skill
        ↓ 选题策略报告
    [Agent 2] Copywriter      ── DeepSeek
        ↓ 文案 + 海报标题锚点
    [Agent 3] Art Director    ── DeepSeek + ZhipuImagePoster Skill
        ↓ 最终海报本地路径
=============================================================
"""

from typing import Callable, Optional
from crewai import Agent, Task, Crew, Process, LLM

from tools import WebSearchTool, ZhipuImagePosterTool


def build_deepseek_llm(api_key: str, temperature: float = 0.7) -> LLM:
    """
    构造 DeepSeek LLM 实例
    CrewAI 通过 LiteLLM 调用 DeepSeek，model 字符串前缀 `deepseek/`
    """
    return LLM(
        model="deepseek/deepseek-chat",
        api_key=api_key,
        temperature=temperature,
    )


def build_crew(
    topic: str,
    deepseek_api_key: str,
    step_callback: Optional[Callable] = None,
    output_dir: str = "./outputs",
):
    """
    根据用户选题，组建完整的 3-Agent Crew

    Parameters
    ----------
    topic : str
        用户输入的选题/关键词
    deepseek_api_key : str
        DeepSeek API Key
    step_callback : callable
        每个 Agent 思考步骤的回调（用于 Streamlit 实时日志）
    output_dir : str
        海报输出目录

    Returns
    -------
    (Crew, List[Task])
        Crew 实例 + 任务列表（用于后续读取每个任务的输出）
    """

    llm = build_deepseek_llm(deepseek_api_key)

    # ============ Skill 装配 ============
    search_skill = WebSearchTool()
    poster_skill = ZhipuImagePosterTool(output_dir=output_dir)

    # ============ Agent 1: 爆款趋势分析师 ============
    trend_analyst = Agent(
        role="爆款趋势分析师",
        goal=(
            f"针对选题 '{topic}'，挖掘小红书 / 抖音 / 微博等平台上"
            f"该话题的用户痛点、爆款标题套路、热门话题标签，"
            f"输出一份结构化的选题策略报告。"
        ),
        backstory=(
            "你是一位深耕新媒体 8 年的内容策略专家，曾操盘过数十个百万爆款选题。"
            "你最擅长用搜索引擎拆解流量密码，能从噪声里提炼出可执行的内容洞察。"
            "你说话精炼，永远用结构化的 Markdown 输出。"
        ),
        tools=[search_skill],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        step_callback=step_callback,
        max_iter=5,
    )

    # ============ Agent 2: 新媒体金牌文案 ============
    copywriter = Agent(
        role="新媒体金牌文案",
        goal=(
            "基于趋势分析师的策略报告，撰写一篇地道的小红书爆款图文，"
            "并提炼一个 ≤15 字、有视觉冲击力的核心海报标题。"
        ),
        backstory=(
            "你是小红书顶流博主背后的金牌文案，擅长用 Emoji、分段干货、"
            "热门话题标签写出停留率极高的种草文。你深知什么样的钩子最抓人。"
            "你的产出从不冗余，永远直击要害。"
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
        step_callback=step_callback,
        max_iter=3,
    )

    # ============ Agent 3: 视觉排版总监 ============
    art_director = Agent(
        role="视觉排版总监",
        goal=(
            "根据文案的核心立意，用英文撰写一段适合 CogView 的图像 Prompt，"
            "然后调用 ZhipuImagePoster 一次性完成 'AI 生图 + 中文叠字' 的整套合成。"
        ),
        backstory=(
            "你是 4A 公司出身的视觉总监，深谙小红书封面美学。"
            "你能把抽象的文字立意精准翻译成画面语言，"
            "也清楚封面文字必须留出空间、底图要避免出现任何字母。"
        ),
        tools=[poster_skill],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        step_callback=step_callback,
        max_iter=4,
    )

    # ============ Task 1: 选题策略报告 ============
    task_trend = Task(
        description=(
            f"针对用户选题【{topic}】，请你执行下列工作：\n"
            f"1. 使用 WebSearch 工具检索该话题在社交媒体上的热门讨论（建议搜 1-2 次）；\n"
            f"2. 总结目标人群的 3-5 个核心痛点；\n"
            f"3. 提炼 3 套经过验证的爆款标题套路（例：『反差感』『数字罗列』"
            f"『身份代入』『悬念钩子』等）；\n"
            f"4. 给出 5 个相关的热门话题标签（#xxx）。\n"
            f"⚠️ 全程使用中文。"
        ),
        expected_output=(
            "一份 Markdown 选题策略报告，含三个章节：\n"
            "### 用户痛点 / ### 爆款标题套路 / ### 热门话题标签"
        ),
        agent=trend_analyst,
    )

    # ============ Task 2: 文案撰写（含海报标题锚点）============
    task_copy = Task(
        description=(
            "基于上一步的选题策略报告，撰写一篇完整的小红书爆款图文：\n"
            "1. 文章标题（≤20 字，要有钩子）；\n"
            "2. 正文 300-500 字，多用 Emoji，分 3-5 个干货段落；\n"
            "3. 文末附 5 个 # 话题标签；\n"
            "4. ⚠️ **最后一行必须**以严格固定格式输出海报标题：\n"
            "       海报标题: xxx\n"
            "   要求 xxx ≤ 15 个汉字、口语化、有视觉冲击力、不含 emoji。\n"
            "   该行将被后续视觉总监正则提取，格式错误会导致海报无法生成。"
        ),
        expected_output=(
            "完整的小红书图文文案 + 最后单独一行 `海报标题: xxx`"
        ),
        agent=copywriter,
        context=[task_trend],
    )

    # ============ Task 3: 视觉合成 ============
    task_visual = Task(
        description=(
            "基于文案的主题与氛围，执行视觉合成：\n"
            "1. 从文案最后一行 `海报标题: xxx` 提取该 xxx 作为 headline 参数；\n"
            "2. 撰写一段高质量的【英文】图像生成 Prompt，要求：\n"
            "   - 符合小红书封面美学（明亮、有质感、构图留白、ins 风/胶片感等）；\n"
            "   - 风格关键词丰富（cinematic、soft lighting、minimalist...）；\n"
            "   - **必须**包含 'no text, no letters, no words, no typography' 以避免"
            "     底图自带文字；\n"
            "3. 调用 ZhipuImagePoster 工具，传入 prompt 和 headline 两个参数；\n"
            "4. 直接返回工具给出的文件路径（如 `海报已生成: ./outputs/poster_final.jpg`），"
            "   并附一句 30 字以内的视觉说明。"
        ),
        expected_output=(
            "形如：\n"
            "海报已生成: ./outputs/poster_final.jpg\n"
            "视觉说明：xxx"
        ),
        agent=art_director,
        context=[task_copy],
    )

    crew = Crew(
        agents=[trend_analyst, copywriter, art_director],
        tasks=[task_trend, task_copy, task_visual],
        process=Process.sequential,
        verbose=True,
    )

    return crew, [task_trend, task_copy, task_visual]
