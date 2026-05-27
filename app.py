"""
=============================================================
小红书 AI Studio - Streamlit 主应用 (v2.0 双垂类聚焦)
=============================================================
本版核心变更:
  · 聚焦 2 个垂类:📚 知识博主 + 🌙 治愈语录
  · 新增 Clarifier 选题深化环节(混合式:3 框架问题 + 1 LLM 个性追问)
  · UI 走 4 步向导:垂类选择 → 输入选题 → Clarifier 追问 → 生成
=============================================================
"""

import os
import re
import glob
import time
import queue
import threading
import traceback

import streamlit as st

from config import config
from agents import run_crew_with_retry
from observability import setup_observability
from verticals import VERTICALS, list_verticals, auto_detect_vertical, get_vertical
from prompts import STYLE_LIBRARY, list_style_keys
from emotion_lexicon import MOOD_TO_EMOTION
from clarifier import (
    ClarifierState, kick_off, submit_framework,
    submit_followup, skip_followup, switch_vertical,
    state_to_short_topic,
)

setup_observability()


# =========================================================
#  页面配置
# =========================================================
st.set_page_config(
    page_title="Xiaohongshu AI Studio",
    page_icon="🌸",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .stApp {
        background:
            radial-gradient(circle at 20% 10%, rgba(192,107,255,0.12), transparent 40%),
            radial-gradient(circle at 80% 90%, rgba(255,107,157,0.12), transparent 40%),
            linear-gradient(135deg, #0a0e27 0%, #1a1f3a 100%);
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1230 0%, #1a1f3a 100%);
    }
    h1, h2, h3 {
        background: linear-gradient(90deg, #ff6b9d, #c06bff, #6b9dff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .stButton > button {
        background: linear-gradient(90deg, #ff6b9d, #c06bff);
        color: white; border: none; border-radius: 10px;
        padding: 0.55rem 2rem; font-weight: 700; letter-spacing: 1px;
        box-shadow: 0 4px 14px rgba(192,107,255,0.35);
        transition: transform .15s, box-shadow .15s;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 22px rgba(192,107,255,0.55);
    }
    /* 垂类选择卡片 */
    .vertical-card {
        background: rgba(255,255,255,0.04);
        border: 2px solid rgba(192,107,255,0.25);
        border-radius: 16px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        cursor: pointer;
        transition: all .2s;
    }
    .vertical-card.active {
        border-color: #ff6b9d;
        background: rgba(255,107,157,0.08);
    }
    .stTextArea textarea, .stTextInput input {
        background: rgba(0,0,0,0.35); color: #e8ecf5;
        border: 1px solid rgba(192,107,255,0.3); border-radius: 8px;
    }
    [data-testid="stExpander"] {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(192,107,255,0.25);
        border-radius: 10px; margin-bottom: 6px;
    }
    .stMarkdown, label, p { color: #d8def0; }
    .step-indicator {
        display: flex; gap: 8px; margin-bottom: 1rem; flex-wrap: wrap;
    }
    .step-pill {
        padding: 4px 12px; border-radius: 12px; font-size: 12px;
        background: rgba(255,255,255,0.05); color: #888;
    }
    .step-pill.active {
        background: linear-gradient(90deg, #ff6b9d, #c06bff);
        color: white; font-weight: 700;
    }
    .step-pill.done {
        background: rgba(0,214,143,0.2); color: #00d68f;
    }
    /* 移动端 */
    @media (max-width: 768px) {
        .block-container { padding: 1rem 0.6rem !important; }
        h1 { font-size: 1.6rem !important; }
        .stButton > button { width: 100%; padding: 0.7rem 1rem; }
        [data-testid="column"] { min-width: 100% !important; }
    }
</style>
""", unsafe_allow_html=True)


# =========================================================
#  Header
# =========================================================
st.markdown("# 🌸 Xiaohongshu AI Studio")
st.markdown("##### 知识博主 × 治愈语录 · 多 Agent 协作 · 选题深化闭环")
st.markdown("---")


# =========================================================
#  Session State 初始化
# =========================================================
def _reset_session():
    """重置整个会话(回到第 1 步)"""
    for k in ["clarifier_state", "logs", "result", "task_outputs",
              "final_score", "running"]:
        st.session_state.pop(k, None)


for key, default in [
    ("clarifier_state", None),
    ("logs", []), ("result", None), ("task_outputs", {}),
    ("running", False), ("final_score", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# =========================================================
#  侧边栏
# =========================================================
with st.sidebar:
    st.markdown("### 🟢 系统状态")
    missing = config.validate()
    if missing:
        st.error("❌ 配置缺失:\n" + "\n".join(f"- `{m}`" for m in missing))
    else:
        st.success("✅ 所有 API Key 已加载")

    with st.expander("🛣️ 模型路由总览", expanded=False):
        for k, v in config.routing_summary().items():
            st.markdown(f"**{k}** → `{v}`")

    st.markdown("---")
    st.markdown("### ⚙️ 生成选项")
    enable_carousel = st.checkbox(
        "📚 生成组图(封面 + 3 张正文图)",
        value=False,
        help="多生成 3 张配图,耗时和成本约 ×2",
    )
    enable_retry = st.checkbox(
        "🔁 启用自检重试",
        value=True,
        help=f"Critic 综合评分 < {config.quality_threshold} 时自动重跑文案",
    )

    st.markdown("---")
    if st.button("🔄 重新开始(清空状态)", use_container_width=True):
        _reset_session()
        st.rerun()


# =========================================================
#  确定当前所处步骤
# =========================================================
state: ClarifierState = st.session_state.clarifier_state

if st.session_state.result is not None:
    current_step = 6  # 已完成生成
elif state is None:
    current_step = 1  # 还没填选题
elif state.stage == "framework":
    current_step = 2  # 填框架问题
elif state.stage == "style_mood":
    current_step = 3  # 选风格+情绪
elif state.stage == "llm_followup":
    current_step = 4  # 答 LLM 追问
elif state.stage == "ready":
    current_step = 5  # 准备启动 Crew
else:
    current_step = 1


def _render_step_indicator():
    """渲染顶部步骤进度条"""
    steps = [
        (1, "1️⃣ 选题"),
        (2, "2️⃣ 细化"),
        (3, "3️⃣ 视觉"),
        (4, "4️⃣ 追问"),
        (5, "5️⃣ 生成"),
        (6, "6️⃣ 成品"),
    ]
    html = '<div class="step-indicator">'
    for n, label in steps:
        cls = "active" if n == current_step else ("done" if n < current_step else "")
        html += f'<span class="step-pill {cls}">{label}</span>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


_render_step_indicator()


# =========================================================
#  Step 1:输入选题 + 垂类选择
# =========================================================
if current_step == 1:
    st.markdown("## 🎯 Step 1 · 选择垂类 & 输入选题")
    st.caption("本工具专注 2 个 AI 生图最友好的垂类。先选方向,再说选题。")

    # 垂类选择(2 张大卡片)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            "<div class='vertical-card'>"
            "<h2 style='margin:0'>📚 知识博主</h2>"
            "<p style='color:#b8c0d8;margin:8px 0'>"
            "学习 · 考试 · 职场 · 技能 · 副业 · 读书笔记"
            "</p>"
            "<p style='color:#999;font-size:12px;margin:0'>"
            "海报:白底卡片 + 干货分点 · 图风:极简插画"
            "</p></div>",
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            "<div class='vertical-card'>"
            "<h2 style='margin:0'>🌙 治愈语录</h2>"
            "<p style='color:#b8c0d8;margin:8px 0'>"
            "情感 · 共鸣 · 治愈 · 毒鸡汤 · 辞职文学"
            "</p>"
            "<p style='color:#999;font-size:12px;margin:0'>"
            "海报:大字居中 + 风景背景 · 图风:梦幻氛围"
            "</p></div>",
            unsafe_allow_html=True,
        )

    # 选择方式
    detect_mode = st.radio(
        "垂类判定方式",
        ["🤖 自动识别(从你的选题里猜)", "📚 我直接选知识博主", "🌙 我直接选治愈语录"],
        horizontal=True,
    )

    topic_input = st.text_input(
        "请输入你的选题(初步想法即可,不用很具体)",
        value="",
        placeholder="例:考研复试 / 副业搞钱 / 深夜失眠 / 辞职文学",
    )

    if st.button("➡️ 下一步:细化选题", use_container_width=True,
                 disabled=bool(missing)):
        if not topic_input.strip():
            st.error("请先输入选题")
        else:
            vertical_choice = None
            if "知识博主" in detect_mode:
                vertical_choice = "knowledge"
            elif "治愈语录" in detect_mode:
                vertical_choice = "healing"
            st.session_state.clarifier_state = kick_off(
                topic_input, user_vertical=vertical_choice
            )
            st.rerun()


# =========================================================
#  Step 2:框架问题表单
# =========================================================
elif current_step == 2:
    vconf = get_vertical(state.vertical)
    st.markdown(f"## 🔍 Step 2 · 细化选题 · {vconf['icon']} {vconf['name']}")

    if state.vertical_auto_detected:
        st.info(f"系统识别为「{vconf['name']}」垂类。如果不对,可在下方切换。")

    # 切换垂类(纠错入口)
    with st.expander("切换垂类?"):
        other = "healing" if state.vertical == "knowledge" else "knowledge"
        other_conf = get_vertical(other)
        if st.button(f"切换到 {other_conf['icon']} {other_conf['name']}",
                     use_container_width=True):
            st.session_state.clarifier_state = switch_vertical(state, other)
            st.rerun()

    st.markdown(f"**原始选题**: `{state.raw_topic}`")
    st.markdown("请回答以下 3 个框架问题,系统据此精准定位内容方向:")

    # 渲染 3 个问题
    with st.form("framework_form"):
        answers = {}
        for q in vconf["clarify_framework"]:
            st.markdown(f"#### {q['question']}")
            if "options" in q:
                answers[q["key"]] = st.radio(
                    q["label"],
                    q["options"],
                    label_visibility="collapsed",
                    key=f"q_{q['key']}",
                )
            else:
                examples = q.get("examples", [])
                placeholder = ("例:" + " / ".join(examples[:3])) if examples else ""
                answers[q["key"]] = st.text_input(
                    q["label"],
                    placeholder=placeholder,
                    label_visibility="collapsed",
                    key=f"q_{q['key']}",
                )

        submit = st.form_submit_button(
            "➡️ 提交,生成个性化追问", use_container_width=True
        )

    if submit:
        missing_ans = [q for q in vconf["clarify_framework"]
                       if q.get("required") and not answers.get(q["key"], "").strip()]
        if missing_ans:
            st.error(f"请填写: {', '.join(q['label'] for q in missing_ans)}")
        else:
            with st.spinner("🧠 Clarifier 正在生成个性化追问..."):
                # 推进到 style_mood 步骤
                st.session_state.clarifier_state.stage = "style_mood"
            st.rerun()


# =========================================================
#  Step 3:选视觉风格 + 情绪 (v2.1 三层 Prompt)
# =========================================================
elif current_step == 3:
    vconf = get_vertical(state.vertical)
    st.markdown(f"## 🎨 Step 3 · 视觉风格 · {vconf['icon']} {vconf['name']}")

    with st.expander("已收集的选题信息", expanded=False):
        for q in vconf["clarify_framework"]:
            ans = state.framework_answers.get(q["key"], "")
            st.markdown(f"- **{q['label']}**: {ans}")

    col_s, col_m = st.columns([1, 1])

    with col_s:
        st.markdown("### 🖼 图像风格")
        style_keys = list_style_keys(state.vertical)
        style_labels = {}
        for sk in style_keys:
            s = STYLE_LIBRARY.get(sk, {})
            style_labels[sk] = f"{s.get('label', sk)} — {s.get('base', '')[:60]}..."

        chosen_style = st.radio(
            "选择海报的视觉风格",
            options=style_keys,
            format_func=lambda k: style_labels.get(k, k),
            key="style_selector",
        )
        # 显示风格预览
        if chosen_style:
            s = STYLE_LIBRARY.get(chosen_style, {})
            st.caption(f"**Tech**: {s.get('tech_specs', '')[:100]}...")

    with col_m:
        if state.vertical == "healing":
            st.markdown("### 🌡 情绪基调")
            mood_options = list(MOOD_TO_EMOTION.keys())
            chosen_mood = st.radio(
                "选择海报传达的情绪",
                options=mood_options,
                format_func=lambda m: f"{m} — {MOOD_TO_EMOTION.get(m, '')}",
                key="mood_selector",
            )
        else:
            st.markdown("### 🌡 情绪基调")
            st.caption("知识博主垂类使用默认「专业理性」配色，无需选择。")
            chosen_mood = ""

    st.markdown("---")
    st.markdown("### 📝 画面细节补充（可选）")
    user_detail = st.text_input(
        "你想在海报里出现什么具体元素？",
        value=state.user_detail,
        placeholder="例: 散落的考研笔记、窗外月光、复古台灯...",
    )

    if st.button("➡️ 下一步: AI 追问", use_container_width=True):
        state.style_key = chosen_style
        state.mood = chosen_mood
        state.user_detail = user_detail
        # 生成 LLM 追问并推进
        with st.spinner("🧠 Clarifier 正在生成个性化追问..."):
            st.session_state.clarifier_state = submit_framework(state, state.framework_answers)
        st.rerun()


# =========================================================
#  Step 4:LLM 个性化追问
# =========================================================
elif current_step == 4:
    vconf = get_vertical(state.vertical)
    st.markdown(f"## 💬 Step 3 · 个性化追问 · {vconf['icon']} {vconf['name']}")

    # 展示已有信息(折叠)
    with st.expander("已收集的选题信息", expanded=False):
        for q in vconf["clarify_framework"]:
            ans = state.framework_answers.get(q["key"], "")
            st.markdown(f"- **{q['label']}**: {ans}")

    # LLM 追问
    st.markdown("### 🤖 Clarifier 想问你最后一个问题:")
    st.markdown(
        f"<div style='background:rgba(192,107,255,0.1);padding:1rem;"
        f"border-radius:10px;border-left:4px solid #c06bff;'>"
        f"{state.llm_followup_question}</div>",
        unsafe_allow_html=True,
    )
    st.markdown("")

    followup_ans = st.text_area(
        "你的回答(可以随意说,30-100 字即可)",
        value="",
        height=100,
        placeholder="说说你的具体想法、想突出的点、想引起的共鸣...",
    )

    col_a, col_b = st.columns([3, 1])
    with col_a:
        if st.button("➡️ 确认,启动 Agent 协作", use_container_width=True):
            if not followup_ans.strip():
                st.error("请简单回答一下,这一句话很关键")
            else:
                st.session_state.clarifier_state = submit_followup(state, followup_ans)
                st.rerun()
    with col_b:
        if st.button("跳过", use_container_width=True):
            st.session_state.clarifier_state = skip_followup(state)
            st.rerun()


# =========================================================
#  Step 5:Crew 执行
# =========================================================
elif current_step == 5:
    vconf = get_vertical(state.vertical)
    st.markdown(f"## 🚀 Step 5 · Agent 协作生成 · {vconf['icon']} {vconf['name']}")

    # 展示最终选题简报
    with st.expander("📋 最终选题简报(传给 Agents)", expanded=True):
        st.markdown(state.final_brief)

    col_a, col_b = st.columns([3, 1])
    with col_a:
        launch = st.button("🚀 启动 4 Agent 协作", use_container_width=True,
                           disabled=st.session_state.running)
    with col_b:
        if st.button("↩️ 改简报", use_container_width=True):
            state.stage = "framework"
            st.rerun()

    if launch:
        # 清理上次产物
        for f in glob.glob("./outputs/poster_*.jpg"):
            try:
                os.remove(f)
            except Exception:
                pass

        for k in ("logs", "result", "task_outputs", "final_score"):
            st.session_state[k] = [] if k == "logs" else None
        st.session_state.running = True

        log_q = queue.Queue()
        holder = {}
        max_attempts = 2 if enable_retry else 1

        def run_in_thread():
            try:
                def step_cb(step_output):
                    try:
                        txt = str(step_output)
                    except Exception:
                        txt = "<step output>"
                    log_q.put({"type": "step", "content": txt[:2000],
                               "ts": time.strftime("%H:%M:%S")})

                def log_fn(msg, typ="info"):
                    log_q.put({"type": typ, "content": msg,
                               "ts": time.strftime("%H:%M:%S")})

                log_fn(f"🧠 选题: {state_to_short_topic(state)}")
                log_fn(f"📊 垂类: {vconf['name']}")

                result, tasks, score = run_crew_with_retry(
                    topic=state.final_brief,
                    step_callback=step_cb,
                    enable_carousel=enable_carousel,
                    max_attempts=max_attempts,
                    log_fn=log_fn,
                    vertical=state.vertical,
                    style_key=state.style_key,
                    mood=state.mood,
                    user_detail=state.user_detail,
                )

                task_outputs = {}
                for i, t in enumerate(tasks):
                    try:
                        out = t.output
                        task_outputs[f"task_{i}"] = (
                            getattr(out, "raw", None)
                            or getattr(out, "raw_output", None)
                            or str(out)
                        )
                    except Exception:
                        task_outputs[f"task_{i}"] = ""

                holder["result"] = str(result)
                holder["task_outputs"] = task_outputs
                holder["final_score"] = score
            except Exception as e:
                tb = traceback.format_exc()
                holder["error"] = str(e)
                log_q.put({"type": "error", "content": f"❌ {e}\n\n{tb}",
                           "ts": time.strftime("%H:%M:%S")})

        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()

        st.markdown("### 🧬 Agent 思考实时流")
        log_container = st.empty()
        progress_bar = st.progress(0, text="Agents working...")
        all_logs = []
        est_steps = 20 if enable_carousel else 16
        if max_attempts > 1:
            est_steps = int(est_steps * 1.5)
        start_ts = time.time()

        while thread.is_alive() or not log_q.empty():
            new_items = []
            while not log_q.empty():
                try:
                    new_items.append(log_q.get_nowait())
                except queue.Empty:
                    break

            if new_items:
                all_logs.extend(new_items)
                with log_container.container():
                    for idx, item in enumerate(all_logs):
                        icon = {"info": "ℹ️", "step": "🤖",
                                "error": "❌", "done": "✅"}.get(item["type"], "📝")
                        first_line = (item["content"][:80].splitlines()[0]
                                      if item["content"] else "")
                        with st.expander(
                            f"{icon}  [{item.get('ts','')}]  "
                            f"{item['type'].upper()}  ·  {first_line}...",
                            expanded=(item["type"] in ("error", "done")
                                      or idx == len(all_logs) - 1),
                        ):
                            st.code(item["content"], language="markdown")

                step_count = sum(1 for x in all_logs if x["type"] == "step")
                pct = min(int(step_count / est_steps * 100), 95)
                if any(x["type"] == "done" for x in all_logs):
                    pct = 100
                progress_bar.progress(
                    pct, text=f"已执行 {step_count} 步 · {int(time.time()-start_ts)}s")

            time.sleep(0.5)

        thread.join()
        progress_bar.progress(100, text="完成 ✅")

        st.session_state.logs = all_logs
        st.session_state.result = holder.get("result")
        st.session_state.task_outputs = holder.get("task_outputs", {})
        st.session_state.final_score = holder.get("final_score")
        st.session_state.running = False
        st.rerun()


# =========================================================
#  Step 6:成品展示
# =========================================================
elif current_step == 6:
    st.markdown("## 🎁 Step 6 · 成品交付")

    task_outputs = st.session_state.task_outputs
    strategy_text = task_outputs.get("task_0", "")
    copy_text_raw = task_outputs.get("task_1", "")
    visual_text = task_outputs.get("task_2", "")
    critic_text = task_outputs.get("task_3", "")

    # 清理文案锚点行
    copy_text = re.sub(r"\n?海报标题[:：][^\n]*", "", copy_text_raw or "")
    copy_text = re.sub(r"\n?分页标题[:：][^\n]*", "", copy_text).strip()

    # 解析评分
    def parse_scores(text):
        if not text: return {}
        return {
            k: int(m.group(1)) for k, p in {
                "copy": r"文案总分[:：]\s*\**\s*(\d+)\s*/\s*100",
                "poster": r"海报总分[:：]\s*\**\s*(\d+)\s*/\s*100",
                "total": r"综合评分[:：]\s*\**\s*(\d+)\s*/\s*100",
            }.items() for m in [re.search(p, text)] if m
        }
    scores = parse_scores(critic_text)

    # 评分卡
    if scores:
        st.markdown("### 📊 质量审核")
        c1, c2, c3 = st.columns(3)

        def badge(s):
            if s is None: return "—", "#888"
            if s >= 80: return f"{s}", "#00d68f"
            if s >= 70: return f"{s}", "#ffaa00"
            return f"{s}", "#ff3d71"

        for col, label, key in [(c1, "文案", "copy"), (c2, "海报", "poster"),
                                 (c3, "综合", "total")]:
            val, color = badge(scores.get(key))
            with col:
                st.markdown(f"""
                <div style='background:linear-gradient(135deg,rgba(255,255,255,0.05),rgba(192,107,255,0.08));
                    border:1px solid rgba(192,107,255,0.3);border-radius:14px;
                    padding:1.2rem;text-align:center;'>
                    <div style='color:#b8c0d8;font-size:14px'>{label}</div>
                    <div style='color:{color};font-size:42px;font-weight:800;line-height:1.2'>{val}</div>
                    <div style='color:#666;font-size:12px'>/ 100</div>
                </div>""", unsafe_allow_html=True)

        total = scores.get("total")
        if total is not None:
            if total >= 80:
                st.success("🟢 爆款潜力,可直接发布")
            elif total >= 70:
                st.warning("🟡 合格,可优化后发布")
            else:
                st.error("🔴 需改进,建议重新生成")

        with st.expander("📋 完整审核报告", expanded=(total or 0) < 80):
            st.markdown(critic_text)

    st.markdown("---")

    # 成品图文
    poster_paths = sorted(glob.glob("./outputs/poster_*.jpg"))
    poster_paths.sort(key=lambda p: 0 if "final" in p else 1)
    cover = next((p for p in poster_paths if "final" in p),
                 poster_paths[0] if poster_paths else None)
    subs = [p for p in poster_paths if "sub" in p]

    col_l, col_r = st.columns([1, 1], gap="large")
    with col_l:
        st.markdown("### 🖼️ 海报封面")
        if cover and os.path.exists(cover):
            st.image(cover, use_container_width=True)
            with open(cover, "rb") as f:
                st.download_button(
                    "⬇️ 下载封面", data=f.read(),
                    file_name="xhs_cover.jpg", mime="image/jpeg",
                    use_container_width=True,
                )
        else:
            st.warning("⚠️ 未生成海报")
        if subs:
            st.markdown("### 📚 正文图")
            sc = st.columns(min(len(subs), 3))
            for i, sp in enumerate(subs):
                with sc[i % len(sc)]:
                    st.image(sp, use_container_width=True)

    with col_r:
        st.markdown("### 📝 文案")
        if copy_text:
            st.text_area("Ctrl+C 复制", value=copy_text, height=500)

    with st.expander("📊 选题策略报告"):
        st.markdown(strategy_text or "无")

    st.markdown("---")
    if st.button("🔄 再做一篇", use_container_width=True):
        _reset_session()
        st.rerun()
