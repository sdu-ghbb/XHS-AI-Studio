"""
=============================================================
小红书 AI Studio - Streamlit 主应用 (v4.0 极简模式)
=============================================================
流程: 输入选题 → 选标题 → 生成 → 成品
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

from dataclasses import dataclass

from config import config
from agents import run_graph


@dataclass
class ClarifierState:
    """用户的选题会话状态"""
    stage: str = "initial"
    raw_topic: str = ""
    final_brief: str = ""


def _kick_off(raw_topic: str) -> ClarifierState:
    return ClarifierState(raw_topic=raw_topic.strip())


def _short_topic(state: ClarifierState) -> str:
    return state.raw_topic

# =========================================================
#  页面配置
# =========================================================
st.set_page_config(
    page_title="小红书 AI Studio",
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
st.markdown("##### 多 Agent 协作 · RAG 风格学习 · 自动图文生成")
st.markdown("---")


# =========================================================
#  Session State 初始化
# =========================================================
def _reset_session():
    """重置整个会话(回到第 1 步)"""
    for k in ["clarifier_state", "logs", "result", "task_outputs",
              "final_score", "running", "headlines", "chosen_headline",
              "headline_running", "headline_error"]:
        st.session_state.pop(k, None)


for key, default in [
    ("clarifier_state", None),
    ("logs", []), ("result", None), ("task_outputs", {}),
    ("running", False), ("final_score", None),
    ("headlines", None), ("chosen_headline", None),
    ("headline_running", False), ("headline_error", None),
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

    enable_carousel = True
    enable_retry = True

    st.markdown("---")
    if st.button("🔄 重新开始(清空状态)", use_container_width=True):
        _reset_session()
        st.rerun()


# =========================================================
#  确定当前所处步骤
# =========================================================
state: ClarifierState = st.session_state.clarifier_state

if st.session_state.result is not None:
    current_step = 4  # 成品
elif state is None:
    current_step = 1  # 输入选题
elif state.stage == "ready" and st.session_state.chosen_headline is None:
    current_step = 2  # 选标题
elif state.stage == "ready" and st.session_state.chosen_headline is not None:
    current_step = 3  # 生成
else:
    current_step = 1


def _render_step_indicator():
    """渲染顶部步骤进度条"""
    steps = [
        (1, "1️⃣ 选题"),
        (2, "2️⃣ 标题"),
        (3, "3️⃣ 生成"),
        (4, "4️⃣ 成品"),
    ]
    html = '<div class="step-indicator">'
    for n, label in steps:
        cls = "active" if n == current_step else ("done" if n < current_step else "")
        html += f'<span class="step-pill {cls}">{label}</span>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


_render_step_indicator()


# =========================================================
#  Step 1: 输入选题
# =========================================================
if current_step == 1:
    st.markdown("## 🎯 Step 1 · 输入你的选题")
    st.caption("输入你想写的小红书内容方向，AI 会自动生成标题候选供你选择。")

    topic_input = st.text_input(
        "你想写什么内容？",
        value="",
        placeholder="例:考研复试 / 副业搞钱 / 深夜失眠 / 职场困惑 / 读书笔记",
    )

    if st.button("➡️ 生成标题候选", use_container_width=True,
                 disabled=bool(missing)):
        if not topic_input.strip():
            st.error("请先输入选题")
        else:
            state = _kick_off(topic_input)
            state.stage = "ready"
            state.final_brief = topic_input.strip()
            st.session_state.clarifier_state = state
            st.rerun()


# =========================================================
#  Step 2: 选择标题候选
# =========================================================
elif current_step == 2:
    st.markdown("## 🎯 Step 2 · 选择标题方向")
    st.caption("系统会先生成 3 个标题候选，你选中最喜欢的一个，再生成完整海报。")

    # 展示选题简报
    with st.expander("📋 选题简报", expanded=False):
        st.markdown(state.final_brief)

    # 生成标题候选
    if st.session_state.headlines is None and not st.session_state.get("headline_running"):
        st.session_state.headline_running = True

        log_placeholder = st.empty()
        progress_placeholder = st.progress(0, text="正在生成标题候选...")

        log_q = queue.Queue()

        def step_cb(out):
            log_q.put(str(out)[:200])

        def log_fn(msg, typ="info"):
            log_q.put(f"[{typ}] {msg}")

        import threading
        result_holder = {}

        def run_headline_gen():
            try:
                from agents import generate_headlines
                headlines = generate_headlines(
                    topic=state.final_brief,
                    step_callback=step_cb,
                    log_fn=log_fn,
                )
                result_holder["headlines"] = headlines
                log_q.put("[done] 完成")
            except Exception as e:
                import traceback
                result_holder["error"] = str(e)
                log_q.put(f"[error] {e}")

        thread = threading.Thread(target=run_headline_gen, daemon=True)
        thread.start()

        all_logs = []
        while thread.is_alive() or not log_q.empty():
            while not log_q.empty():
                msg = log_q.get()
                all_logs.append(msg)
                if msg.startswith("[done]"):
                    progress_placeholder.progress(100)
                elif msg.startswith("[error]"):
                    progress_placeholder.error(msg)
                else:
                    progress_placeholder.progress(min(len(all_logs) * 20, 95))

            time.sleep(0.3)

        st.session_state.headlines = result_holder.get("headlines", [])
        st.session_state.headline_error = result_holder.get("error")
        st.session_state.headline_running = False
        st.rerun()

    # 展示标题候选 + 选标题
    if st.session_state.headlines:
        headlines = st.session_state.headlines
        st.markdown("### 请选择一个标题方向：")

        # 渲染标题卡片
        chosen = None
        cols = st.columns(min(len(headlines), 3))
        for i, h in enumerate(headlines):
            with cols[i % len(cols)]:
                if st.button(
                    f"📝 **标题 {i+1}**\n\n{h}",
                    use_container_width=True,
                    key=f"headline_{i}",
                ):
                    chosen = h

        if chosen:
            st.session_state.chosen_headline = chosen
            st.session_state.headlines = headlines  # keep for display
            st.rerun()

        st.markdown("---")
        if st.button("🔄 重新生成标题", use_container_width=True):
            st.session_state.headlines = None
            st.rerun()
        if st.button("↩️ 改选题", use_container_width=True):
            st.session_state.headlines = None
            st.session_state.chosen_headline = None
            st.session_state.clarifier_state = None
            st.rerun()

    elif st.session_state.get("headline_error"):
        st.error(f"标题生成失败: {st.session_state.headline_error}")
        if st.button("重试", use_container_width=True):
            st.session_state.headlines = None
            st.rerun()


# =========================================================
#  Step 3: 生成（Crew 执行）
# =========================================================
elif current_step == 3:
    st.markdown("## 🚀 Step 3 · 多 Agent 协作生成")

    # 展示已选标题
    if st.session_state.get("chosen_headline"):
        st.success(f"✅ 已选标题: **{st.session_state.chosen_headline}**")

    with st.expander("📋 最终选题简报", expanded=True):
        brief = state.final_brief
        if st.session_state.get("chosen_headline"):
            brief += f"\n\n**用户选定标题**: {st.session_state.chosen_headline}"
        st.markdown(brief)

    col_a, col_b = st.columns([3, 1])
    with col_a:
        launch = st.button("🚀 启动 4 Agent 协作", use_container_width=True,
                           disabled=st.session_state.running)
    with col_b:
        if st.button("↩️ 选其他标题", use_container_width=True):
            st.session_state.chosen_headline = None
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
                _last_agent = [""]
                _step_no = [0]

                def _detect_role(text: str) -> str:
                    import re as _re
                    m = _re.search(r'Agent[：:]\s*(\S+)', text)
                    if m: return m.group(1)[:20]
                    for kw in ["资料搜集", "金牌文案", "新媒体金牌文案", "视觉排版总监", "审核总监"]:
                        if kw in text:
                            return kw[:20]
                    return ""

                def step_cb(step_output):
                    try:
                        txt = str(step_output)
                    except Exception:
                        txt = "<step output>"

                    _step_no[0] += 1
                    role = _detect_role(txt)

                    if role and role != _last_agent[0]:
                        _last_agent[0] = role
                        emoji_map = {"资料搜集": "🔍", "文案": "✍️", "视觉": "🎨", "审核": "🔎"}
                        emoji = next((v for k, v in emoji_map.items() if k in role), "🤖")
                        log_q.put({"type": "info", "content": f"{emoji} {role} 开始工作...",
                                   "ts": time.strftime("%H:%M:%S")})

                    # 每步心跳：不依赖角色检测，保证可见进度
                    label = f"{role} · 第 {_step_no[0]} 步" if role else f"Agent 思考中 · 第 {_step_no[0]} 步"
                    log_q.put({"type": "info", "content": f"🤖 {label}",
                               "ts": time.strftime("%H:%M:%S")})

                    log_q.put({"type": "step", "content": txt[:2000],
                               "ts": time.strftime("%H:%M:%S")})

                def log_fn(msg, typ="info"):
                    log_q.put({"type": typ, "content": msg,
                               "ts": time.strftime("%H:%M:%S")})

                # 注入用户选中的标题
                topic_brief = state.final_brief
                if st.session_state.get("chosen_headline"):
                    topic_brief += (
                        f"\n\n⚠️ 用户已选定以下标题，请确保产出完全围绕此标题展开：\n"
                        f"【选定标题】{st.session_state.chosen_headline}"
                    )
                    log_fn(f"🎯 选定标题: {st.session_state.chosen_headline}")

                log_fn(f"🧠 选题: {_short_topic(state)}")

                state = run_graph(
                    topic=topic_brief,
                    enable_carousel=enable_carousel,
                    max_attempts=max_attempts,
                    on_event=None,  # Streamlit 用 log_q 就好，不走 SSE
                )

                task_outputs = {
                    "research": state.get("research_context", "")[:2000],
                    "copy": state.get("copy_output", ""),
                    "critic": state.get("critic_output", ""),
                    "visual": "\n".join(state.get("poster_paths", [])),
                    "task_0": state.get("research_context", "")[:2000],
                    "task_1": state.get("copy_output", ""),
                    "task_2": state.get("critic_output", ""),
                    "task_3": "",
                }

                holder["result"] = state.get("copy_output", "")
                holder["task_outputs"] = task_outputs
                holder["final_score"] = state.get("score", 0)
            except Exception as e:
                tb = traceback.format_exc()
                holder["error"] = str(e)
                log_q.put({"type": "error", "content": f"❌ {e}\n\n{tb}",
                           "ts": time.strftime("%H:%M:%S")})

        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()

        # 定时心跳线程——不依赖 CrewAI step_cb 频率，保证进度可见
        hb_stop = threading.Event()
        def heartbeat():
            while not hb_stop.is_set():
                hb_stop.wait(3.0)  # 每 3 秒
                if not hb_stop.is_set():
                    elapsed = int(time.time() - start_ts)
                    log_q.put({"type": "info", "content": f"⏳ 正在生成... 已耗时 {elapsed} 秒",
                               "ts": time.strftime("%H:%M:%S")})
        hb_thread = threading.Thread(target=heartbeat, daemon=True)

        st.markdown("### 🧬 生成进度")
        log_container = st.empty()
        progress_bar = st.progress(0, text="🚀 启动中...")
        status_text = st.empty()
        all_logs = []
        start_ts = time.time()
        hb_thread.start()

        # 阶段进度权重
        PHASE_WEIGHTS = {"搜集": 15, "文案": 35, "审核": 15, "海报": 35}

        def _detect_phase(content: str) -> str:
            """从日志内容推断当前阶段"""
            for kw in ["搜集", "搜索", "资料"]:
                if kw in content: return "搜集"
            for kw in ["文案", "撰写", "写作"]:
                if kw in content: return "文案"
            for kw in ["审核", "评分", "Critic"]:
                if kw in content: return "审核"
            for kw in ["海报", "视觉", "生图", "ImagePoster"]:
                if kw in content: return "海报"
            return ""

        def _calc_progress(logs: list) -> int:
            """根据已出现的阶段计算进度"""
            seen = set()
            for item in logs:
                phase = _detect_phase(item.get("content", ""))
                if phase: seen.add(phase)
            pct = sum(PHASE_WEIGHTS.get(p, 5) for p in seen)
            return min(pct, 95)

        while thread.is_alive() or not log_q.empty():
            new_items = []
            while not log_q.empty():
                try:
                    new_items.append(log_q.get_nowait())
                except queue.Empty:
                    break

            if new_items:
                all_logs.extend(new_items)

                # 只展示最近的 log_fn 消息（阶段摘要），step 细节默认折叠
                with log_container.container():
                    visible_logs = [l for l in all_logs if l.get("type") != "step"]
                    step_logs = [l for l in all_logs if l.get("type") == "step"]

                    for idx, item in enumerate(visible_logs):
                        typ = item.get("type", "info")
                        icon = {"info": "📌", "done": "✅", "error": "❌"}.get(typ, "📌")
                        ts = item.get("ts", "")
                        content = item.get("content", "")
                        st.markdown(f"{icon} `{ts}` {content}")

                    # Step 细节折叠收纳
                    if step_logs:
                        with st.expander(f"🔍 Agent 内部推理 · 共 {len(step_logs)} 步", expanded=False):
                            for s in step_logs[-6:]:  # 只显示最近 6 条
                                raw = s.get("content", "")
                                first_line = raw.split("\n")[0][:100] if raw else ""
                                st.caption(f"`{s.get('ts','')}` {first_line}...")

                # 更新进度
                pct = _calc_progress(all_logs)
                elapsed = int(time.time() - start_ts)
                phase = _detect_phase(all_logs[-1].get("content", "")) if all_logs else ""
                phase_label = f" · {phase}阶段" if phase else ""

                if any(l.get("type") == "done" for l in all_logs):
                    pct = 100
                progress_bar.progress(pct, text=f"⏱ {elapsed}秒{phase_label}")

                # 计算已完成阶段
                done_phases = []
                for p in ["搜集", "文案", "审核"]:
                    for l in all_logs:
                        if p in l.get("content", ""):
                            done_phases.append(p)
                            break
                status_text.caption("已完成: " + " → ".join(done_phases) if done_phases else "准备中...")

            time.sleep(0.5)

        hb_stop.set()
        thread.join()
        progress_bar.progress(100, text="完成 ✅")

        st.session_state.logs = all_logs
        st.session_state.result = holder.get("result")
        st.session_state.task_outputs = holder.get("task_outputs", {})
        st.session_state.final_score = holder.get("final_score")
        st.session_state.running = False
        st.rerun()


# =========================================================
#  Step 4:成品展示
# =========================================================
elif current_step == 4:
    st.markdown("## 🎁 Step 4 · 成品交付")

    task_outputs = st.session_state.task_outputs
    # 优先按 Agent 角色取，兼容索引（不再硬编码依赖 task_N 序号）
    research_text = task_outputs.get("research") or task_outputs.get("task_0", "")
    copy_text_raw = task_outputs.get("copy") or task_outputs.get("task_1", "")
    critic_text = task_outputs.get("critic") or task_outputs.get("task_2", "")
    visual_text = task_outputs.get("visual") or task_outputs.get("task_3", "")

    # 清理文案锚点行
    copy_text = re.sub(r"\n?海报标题[:：][^\n]*", "", copy_text_raw or "")
    copy_text = re.sub(r"\n?分页标题[:：][^\n]*", "", copy_text).strip()

    # 改进建议（折叠展示，不看也不影响使用）
    if critic_text and "改进建议" in critic_text:
        with st.expander("💡 改进建议（可选参考）", expanded=False):
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

    st.markdown("---")
    if st.button("🔄 再做一篇", use_container_width=True):
        _reset_session()
        st.rerun()
