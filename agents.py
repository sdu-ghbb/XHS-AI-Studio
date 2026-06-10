"""
=============================================================
TuLun AI Studio — Agent 编排引擎 (LangGraph)
=============================================================
基于 LangGraph StateGraph：节点内直接调 LLM API →
阶段事件实时推前端 → 四个阶段 100% 可控

节点: Research → Copywriter → Critic ⇄ (retry) → Visual → END
=============================================================
"""

import os
import re
import time
import json
import threading
from typing import Optional, Callable, Dict, Any, List, TypedDict, Annotated
from openai import OpenAI

from config import config
from knowledge_base import get_kb
from tools import BochaSearchTool, SmartImagePosterTool, ShadowKBTool


# =========================================================
#  State 定义
# =========================================================

class GraphState(TypedDict, total=False):
    topic: str
    enable_carousel: bool
    max_attempts: int
    attempt: int
    research_context: str
    style_examples: str
    copy_output: str
    headline: str
    critic_output: str
    score: int
    feedback: str
    poster_paths: List[str]


# 模块级事件回调（避免 LangGraph 序列化 Callable）
_event_cb: Optional[Callable] = None


def _emit(etype: str, data: dict):
    if _event_cb:
        try:
            _event_cb(etype, data)
        except Exception:
            pass


# =========================================================
#  LLM 客户端
# =========================================================

def _get_client() -> OpenAI:
    return OpenAI(
        api_key=config.deepseek_api_key,
        base_url=config.deepseek_base_url,
        timeout=120,
    )


def _llm_call(
    system: str,
    user: str,
    temperature: float = 0.7,
    stream: bool = False,
    on_token: Optional[Callable] = None,
) -> str:
    """调用 DeepSeek，可选 streaming"""
    client = _get_client()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    if stream and on_token:
        full = []
        resp = client.chat.completions.create(
            model=config.deepseek_chat_model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        for chunk in resp:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                full.append(delta)
                on_token(delta)
        return "".join(full)
    else:
        resp = client.chat.completions.create(
            model=config.deepseek_chat_model,
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""


# =========================================================
#  工具执行辅助
# =========================================================

def _run_tool(tool, query: str) -> str:
    """同步执行 CrewAI 工具（基类 BaseTool._run）"""
    try:
        return tool._run(query)
    except Exception as e:
        return f"[工具错误] {e}"


# =========================================================
#  样式 RAG 预处理
# =========================================================

def _fetch_style_examples(topic: str) -> str:
    """从影子题库检索爆款范文"""
    try:
        kb = get_kb()
        if kb.is_ready():
            results = kb.search_style(query=topic, top_k=5)
            if results:
                return kb.format_style_for_agent(results)
    except Exception as e:
        print(f"[graph] style RAG failed: {e}")
    return ""


# =========================================================
#  Node 1: Researcher
# =========================================================

def research_node(state: GraphState) -> GraphState:
    topic = state["topic"]
    _emit("log", {"content": f"🔍 搜索资料中..."})

    kb_tool = ShadowKBTool()
    search_tool = BochaSearchTool()

    style = _fetch_style_examples(topic)
    state["style_examples"] = style
    if style:
        _emit("log", {"content": f"📚 找到 {style.count('【范文')} 篇相关范文"})

    # 搜索影子题库
    kb_result = _run_tool(kb_tool, topic)
    kb_count = kb_result.count("【")
    _emit("log", {"content": f"📖 资料库检索到 {kb_count} 条相关内容"})

    # 搜索网络（取 topic 第一行作为关键词，直接搜，不加无意义后缀）
    _search_topic = topic.split("\n")[0].strip()[:50]
    web_result = _run_tool(search_tool, _search_topic)

    import re as _re, requests as _req
    import trafilatura
    _fetched = ""
    _fetched_cnt = 0
    # 优先抓新闻站/知乎，跳过垃圾站
    _good = ['news.','iqilu','zhihu','qingdaonews','qtv','sdnews','people','sina','sohu','xiaohongshu']
    _bad = ['foodmate','search.php','baike','wiki','login','signup','tag/','/search','58.com','ganji.com','sohu.com','qyer.com','mafengwo','ctrip','tuniu']
    urls_raw = list(set(_re.findall(r'https?://[^\s)\]）]+', web_result)))
    urls_raw = [u for u in urls_raw if not any(b in u for b in _bad)]
    # 去重：http/https 同一个域名+路径视为相同
    seen, urls = set(), []
    for u in urls_raw:
        norm = _re.sub(r'^https?://', '', u)  # 去掉协议
        if norm not in seen:
            seen.add(norm); urls.append(u)
    urls = sorted(urls, key=lambda u: 0 if any(d in u for d in _good) else 1)
    for _url in urls[:5]:
        if _fetched_cnt >= 3: break
        try:
            _resp = _req.get(_url, timeout=12, headers={
                "User-Agent": "Mozilla/5.0 (compatible; Bot/1.0)"
            })
            if _resp.status_code == 200:
                _resp.encoding = _resp.apparent_encoding or 'utf-8'
                _text = trafilatura.extract(_resp.text,
                    include_links=False, include_images=False,
                    include_tables=False, output_format="txt")
                if _text and len(_text) > 80:
                    _fetched += f"\n\n[来源 {_url[:60]}] {_text[:1200]}"
                    _fetched_cnt += 1
                    _emit("log", {"content": f"🌐 抓取网页: {_url[:60]}... ({len(_text)} 字)"})
        except Exception as _e:
            print(f"[research] fetch {_url[:40]} failed: {_e}")

    # 用 LLM 整理
    system = (
        "你是信息整理专家。把资料中和主题相关的核心信息提取出来，写成 300 字以内简报。\n"
        "资料里有什么就写什么。资料不够时，可以补充该话题的通用建议和观察，\n"
        "但不要编造具体地名、店名、人名。"
    )
    user = (
        f"主题：{topic}\n"
        f"===== 题库 =====\n{kb_result}\n"
        f"===== 摘要 =====\n{web_result}\n"
        f"===== 全文 =====\n{_fetched}\n"
        f"请整理简报。"
    )
    research = _llm_call(system, user, temperature=0.3)

    state["research_context"] = research
    _emit("log", {"content": f"📋 研究简报: {research[:120]}..."})
    _emit("phase", {"phase": "search", "label": "🔍 搜索完成"})
    return state


# =========================================================
#  Node 2: Copywriter
# =========================================================

_COPY_SYSTEM = (
    "你是深耕小红书 3 年的金牌文案，专精爆款笔记创作。\n"
    "写作风格：口语化、有情绪、有干货、像朋友聊天。\n"
    "每段开头用 1 个 emoji，正文 300-500 字。\n"
    "⚠️ 文案最后必须严格按以下格式输出（不要省略任何一行）：\n"
    "#话题1 #话题2 #话题3 #话题4 #话题5\n"
    "海报标题: 你的标题\n"
    "分页标题: 分页1 | 分页2 | 分页3\n"
    "（话题标签 5 个，分页标题用 | 分隔刚好 3 个，每个 5-10 字）\n"
    "格式禁令：禁用 **加粗**、## 标题、`代码`、> 引用、- 列表 —— 纯文字+emoji。\n"
    "禁止 AI 八股（综上所述/值得注意的是/让我们）。\n"
    "⚠️ 直接输出文案成品。禁止输出分析过程、禁止输出「范文分析」「爆款逻辑」。"
)

def copywriter_node(state: GraphState) -> GraphState:
    topic = state["topic"]
    research = state.get("research_context", "")
    style = state.get("style_examples", "")
    feedback = state.get("feedback", "")

    # 组装 user prompt
    parts = [f"选题：{topic}\n"]

    if style:
        parts.append(f"══════ 爆款范文（请学习风格）══════\n{style}\n═════════════════════════\n")

    if research:
        parts.append(f"参考资料：\n{research}\n")

    parts.append("请撰写小红书爆款图文。")

    if feedback:
        prev = state.get("copy_output", "")
        parts.append(
            f"\n===== ⚠️ 重写任务 =====\n"
            f"上一版被审核员驳回，评分不达标。以下是问题：\n{feedback}\n"
            f"===== 被驳回的原文（请避免同样问题）=====\n{prev[:800]}\n"
            f"请重新撰写一篇更好的，不要重复被驳回的内容。"
        )

    user = "\n".join(parts)

    # ---- 流式写文案 ----
    copy_text = _llm_call(_COPY_SYSTEM, user, temperature=0.85)

    # 提取海报标题
    headline = ""
    m = re.search(r'海报标题[：:]\s*(.+?)(?:\n|$)', copy_text)
    if m:
        headline = m.group(1).strip()
    if not headline:
        first = copy_text.strip().split("\n")[0]
        headline = re.sub(r'[^\w一-鿿]', '', first)[:15] or "小红书"
        _emit("log", {"content": "⚠️ 未找到海报标题，使用兜底标题"})

    state["copy_output"] = copy_text
    state["headline"] = headline

    _emit("log", {"content": f"📝 文案生成完成，{len(copy_text)} 字"})
    # 输出文案开头预览
    preview = re.sub(r'\n+', ' ', copy_text)[:100]
    _emit("log", {"content": f"📌 预览: {preview}..."})
    _emit("phase", {"phase": "copy", "label": "✍️ 撰写完成"})

    return state


# =========================================================
#  Node 3: Critic
# =========================================================

_CRITIC_SYSTEM = (
    "你是头部 MCN 内容质量总监，过手爆款超 500 篇。\n"
    "严格审核文案质量，打分必苛刻——80 分以上才有爆款潜力。\n\n"
    "评分维度（每项 0-25）：\n"
    "- 标题吸引力：数字/身份词/反差/悬念\n"
    "- 地道风格：口语化、像小红书真人\n"
    "- 内容密度：有真干货/真感受\n"
    "- 事实核查：文案中的任何具体信息（地点、名称、数据、事件、人物等）是否与参考资料一致，有无凭空编造或张冠李戴\n\n"
    "严格按以下格式输出（不要任何其他文字）：\n"
    "综合评分: X/100\n"
    "改进建议:\n"
    "- 具体到能照着改的建议（事实有误的要指出；评分 >= 85 写「无需修改」）"
)

def critic_node(state: GraphState) -> GraphState:
    copy_text = state.get("copy_output", "")
    research = state.get("research_context", "")

    user = (
        f"===== 参考资料（事实依据）=====\n{research}\n\n"
        f"===== 待审核文案 =====\n{copy_text}\n\n"
        f"请比对文案与资料，检查是否有编造的内容。"
    )
    critic_out = _llm_call(_CRITIC_SYSTEM, user, temperature=0.2)

    # 提取评分
    score = 0
    m = re.search(r'综合评分[：:]\s*(\d+)', critic_out)
    if m:
        score = int(m.group(1))

    # 提取建议
    feedback = ""
    m = re.search(r'改进建议[：:]?\s*\n(.+)', critic_out, re.DOTALL)
    if m:
        feedback = m.group(1).strip()[:500]

    state["critic_output"] = critic_out
    state["score"] = score
    state["feedback"] = feedback
    state["attempt"] = state.get("attempt", 0) + 1  # 递增重试计数（初始 0，第一次 critic 后变 1）

    stars = "⭐" * max(1, score // 20) + "☆" * (5 - max(1, score // 20))
    if score >= config.quality_threshold:
        _emit("log", {"content": f"✅ 审核通过 {score}/100 {stars}", "type": "done"})
    else:
        _emit("log", {"content": f"⚠️ 评分 {score}/100 {stars}，自动优化中..."})

    _emit("phase", {"phase": "critic", "label": "🔎 审核完成"})
    return state


# =========================================================
#  Node 4: Visual (Art Director)
# =========================================================

def visual_node(state: GraphState) -> GraphState:
    headline = state.get("headline", "")
    copy_text = state.get("copy_output", "")
    enable_carousel = state.get("enable_carousel", False)
    _emit("log", {"content": "🎨 开始生成海报..."})

    prompt_system = (
        "你是 4A 视觉总监。生成英文图像 prompt，描述画面场景/色彩/构图。\n"
        "必须包含 'no people, no text, no letters'。\n"
        "⚠️ 每次生成的画面主题要不同——封面突出主题氛围，分页图各画不同的具体场景。\n"
        "只输出 prompt，不要解释。"
    )

    # 封面 + 分页各用不同风格参数，避免四张图雷同
    _variety = [
        "warm tones, soft lighting, close-up shot, shallow depth of field",
        "cool tones, bright daylight, wide angle, clean minimalist composition",
        "vibrant colors, dramatic side lighting, 45-degree angle, rich textures",
        "pastel palette, diffused natural light, flat lay overhead, airy atmosphere",
    ]
    cover_prompt = _llm_call(
        prompt_system,
        f"封面主题：{headline}\n风格倾向：{_variety[0]}\n文案：{copy_text[:300]}",
        temperature=0.6
    )
    _emit("log", {"content": "🖊️ 封面画面已构思"})

    sub_headlines = ""
    sub_prompts = ""
    if enable_carousel:
        raw_subs = ""
        # 策略1: 同一行 "分页标题: A | B | C"
        m = re.search(r'分页标题[：:]\s*(.+?)(?:\n|$)', copy_text)
        if m: raw_subs = m.group(1).strip()
        # 策略2: 分页标题单独一行，内容在下一行
        if not raw_subs:
            m = re.search(r'分页标题[：:]\s*\n\s*(.+?)(?:\n\n|\n$|$)', copy_text)
            if m: raw_subs = m.group(1).strip()
        # 策略3: 从头到尾找所有 "A | B | C" 格式的行
        if not raw_subs:
            for line in copy_text.split("\n"):
                if "|" in line or "｜" in line:
                    parts = [s.strip() for s in re.split(r'[|｜]', line) if s.strip()]
                    if len(parts) >= 2:
                        raw_subs = line.strip(); break

        if raw_subs:
            raw_subs = re.sub(r'\*\*', '', raw_subs)
            subs = [s.strip() for s in re.split(r'[|｜]', raw_subs) if s.strip()]
            if subs:
                # 不够 3 个就让 LLM 补
                if len(subs) < 3:
                    fill = _llm_call(
                        "根据已有标题和主题，补充分页标题到恰好 3 个。用 | 分隔，只输出结果。",
                        f"主题:{headline}\n已有: {' | '.join(subs)}\n补充到 3 个:", temperature=0.5)
                    extra = [s.strip() for s in re.split(r'[|｜]', fill.strip()) if s.strip()]
                    if extra:
                        subs = (subs + extra)[:3]
                        _emit("log", {"content": f"📑 自动补齐分页标题到 {len(subs)} 个"})
                sub_headlines = " | ".join(subs[:3])
                _emit("log", {"content": f"📑 提取分页标题: {sub_headlines}"})
                sub_prompt_list = []
                for i, s in enumerate(subs[:3]):
                    p = _llm_call(
                        prompt_system,
                        f"分页主题：{s}\n风格倾向：{_variety[i+1]}\n整体文案：{copy_text[:200]}",
                        temperature=0.6
                    )
                    sub_prompt_list.append(p.strip())
                sub_prompts = " ||| ".join(sub_prompt_list)
                _emit("log", {"content": f"🖊️ 分页画面已构思 ({len(subs)} 页)"})
        if not sub_headlines:
            _emit("log", {"content": "⚠️ 未找到分页标题，仅生成封面"})

    _emit("log", {"content": "🖼️ 正在生成图片，请耐心等待..."})
    poster_tool = SmartImagePosterTool(output_dir=config.output_dir)
    try:
        poster_tool._run(
            prompt=cover_prompt.strip(),
            headline=headline,
            sub_headlines=sub_headlines,
            sub_prompts=sub_prompts,
        )
        import glob
        paths = sorted(glob.glob(os.path.join(config.output_dir, "poster_*.jpg")))
        paths.sort(key=lambda p: 0 if "final" in p else 1)
        state["poster_paths"] = paths
        _emit("log", {"content": f"🖼️ 图片生成完成 ({len(paths)} 张)"})
        _emit("phase", {"phase": "visual", "label": "🎨 生图完成"})
    except Exception as e:
        _emit("log", {"content": f"❌ 图片生成失败: {e}", "type": "error"})
        state["poster_paths"] = []

    return state


# =========================================================
#  Graph 构建 & 主入口
# =========================================================

from langgraph.graph import StateGraph, END


# =========================================================
#  轻量函数：选题 → 3 个细化方向
# =========================================================

_HEADLINE_SYSTEM = (
    "你是小红书爆款标题专家。根据用户给的话题，生成 3 个不同风格的标题。\n\n"
    "规则：\n"
    "  · 每个标题 ≤20 字（含标点），有吸引力但不夸张\n"
    "  · 3 个标题从不同角度切入（经验分享 / 干货总结 / 避坑提醒）\n"
    "  · 口语化，像真人写的，别像营销号\n"
    "  · 不要编造具体数字和细节（如'双非''3个大坑'这种用户没说就别编）\n"
    "  · 紧扣话题，不要跑题\n\n"
    "严格按格式输出：\n"
    "标题1: xxx\n"
    "标题2: xxx\n"
    "标题3: xxx"
)

def generate_headlines(topic: str) -> list:
    """选题 → 3 个不同风格的标题"""
    resp = _llm_call(_HEADLINE_SYSTEM, f"话题：{topic}\n请为这个话题生成 3 个爆款标题。", temperature=0.9)
    headlines = []
    for m in re.finditer(r'标题\s*\d\s*[：:]\s*(.+?)(?:\n|$)', resp):
        h = m.group(1).strip().rstrip("。，, ")
        if h and len(h) >= 4:
            headlines.append(h)
    if len(headlines) < 3:
        for line in resp.split("\n"):
            line = line.strip().strip("-*•·0123456789.：: ")
            if line and 5 < len(line) < 30 and line not in headlines:
                headlines.append(line)
            if len(headlines) >= 3:
                break
    return headlines[:3]


def build_graph() -> StateGraph:
    wf = StateGraph(GraphState)

    wf.add_node("research", research_node)
    wf.add_node("copywriter", copywriter_node)
    wf.add_node("critic", critic_node)
    wf.add_node("visual", visual_node)

    wf.set_entry_point("research")
    wf.add_edge("research", "copywriter")
    wf.add_edge("copywriter", "critic")

    def _after_critic(state: GraphState) -> str:
        score = state.get("score", 0)
        attempt = state.get("attempt", 1)
        max_attempts = state.get("max_attempts", 2)
        if score >= config.quality_threshold or attempt >= max_attempts:
            return "visual"
        return "copywriter"

    wf.add_conditional_edges("critic", _after_critic, {
        "copywriter": "copywriter",
        "visual": "visual",
    })
    wf.add_edge("visual", END)

    return wf.compile()


# 模块级单例
_graph = None

def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_graph(
    topic: str,
    enable_carousel: bool = False,
    max_attempts: int = 2,
    on_event: Optional[Callable] = None,
) -> dict:
    """
    LangGraph 主入口 —— 替代 run_crew_with_retry

    on_event(event_type: str, data: dict)
      - "phase": {"phase": "search/copy/critic/visual", "label": "..."}
      - "log": {"content": "...", "type": "info/done/error"}
      - "token": {"content": "..."}   # 逐字 streaming（预留）
    """
    global _event_cb
    _event_cb = on_event

    graph = get_graph()
    initial_state: GraphState = {
        "topic": topic,
        "enable_carousel": enable_carousel,
        "max_attempts": max_attempts,
        "attempt": 0,
        "research_context": "",
        "style_examples": "",
        "copy_output": "",
        "headline": "",
        "critic_output": "",
        "score": 0,
        "feedback": "",
        "poster_paths": [],
    }

    final = graph.invoke(initial_state)
    return final
