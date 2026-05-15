"""
=============================================================
小红书爆款图文生成 Agent —— Streamlit 主应用
=============================================================
布局：
    ┌── 侧边栏 ──┐    ┌─────────── 主体 ───────────┐
    │ API Key  │    │  🧬 Agent 思考实时流          │
    │ 选题输入  │    │  ───────────────────         │
    │ 启动按钮  │    │  🎁 成品交付（左图 + 右文）   │
    └─────────┘    └────────────────────────────┘
=============================================================
"""

import os
import re
import time
import queue
import threading
import traceback

import streamlit as st

from agents import build_crew


# =========================================================
#  页面配置 + 全局 CSS（科技感主题）
# =========================================================
st.set_page_config(
    page_title="Xiaohongshu AI Studio",
    page_icon="🌸",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    /* 全局深色科技感背景 */
    .stApp {
        background:
            radial-gradient(circle at 20% 10%, rgba(192,107,255,0.12), transparent 40%),
            radial-gradient(circle at 80% 90%, rgba(255,107,157,0.12), transparent 40%),
            linear-gradient(135deg, #0a0e27 0%, #1a1f3a 100%);
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1230 0%, #1a1f3a 100%);
    }
    /* 渐变标题 */
    h1, h2, h3 {
        background: linear-gradient(90deg, #ff6b9d, #c06bff, #6b9dff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    /* 按钮 */
    .stButton > button {
        background: linear-gradient(90deg, #ff6b9d, #c06bff);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.55rem 2rem;
        font-weight: 700;
        letter-spacing: 1px;
        box-shadow: 0 4px 14px rgba(192, 107, 255, 0.35);
        transition: transform .15s, box-shadow .15s;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 22px rgba(192, 107, 255, 0.55);
    }
    /* Expander 卡片化 */
    [data-testid="stExpander"] {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(192, 107, 255, 0.25);
        border-radius: 10px;
        margin-bottom: 6px;
    }
    /* 文本域 */
    .stTextArea textarea {
        background: rgba(0,0,0,0.35);
        color: #e8ecf5;
        border: 1px solid rgba(192,107,255,0.3);
        border-radius: 8px;
    }
    /* 文字主色 */
    .stMarkdown, label, p {
        color: #d8def0;
    }
</style>
""", unsafe_allow_html=True)


# =========================================================
#  顶部标题
# =========================================================
st.markdown("# 🌸 Xiaohongshu AI Studio")
st.markdown("##### 多 Agent 协作 · 一键产出小红书爆款图文")
st.caption("Powered by CrewAI · DeepSeek · 智谱 CogView · Pillow")
st.markdown("---")


# =========================================================
#  Session State 初始化
# =========================================================
for key, default in [
    ("logs", []),
    ("result", None),
    ("task_outputs", {}),
    ("poster_path", None),
    ("running", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# =========================================================
#  侧边栏：API Key + 选题输入
# =========================================================
with st.sidebar:
    st.markdown("### ⚙️ 模型配置")

    deepseek_key = st.text_input(
        "DeepSeek API Key",
        type="password",
        value=os.getenv("DEEPSEEK_API_KEY", ""),
        help="逻辑与文案大脑（必填）",
    )
    zhipu_key = st.text_input(
        "ZhipuAI API Key",
        type="password",
        value=os.getenv("ZHIPUAI_API_KEY", ""),
        help="视觉生图大脑 · CogView-3-Plus（必填）",
    )
    tavily_key = st.text_input(
        "Tavily API Key（可选）",
        type="password",
        value=os.getenv("TAVILY_API_KEY", ""),
        help="留空则自动使用 DuckDuckGo 检索",
    )

    st.markdown("---")
    st.markdown("### 🎯 选题输入")
    topic = st.text_input(
        "请输入选题关键词",
        value="秋冬通勤穿搭",
        placeholder="例：周末市集 / 学生党护肤 / 通勤穿搭",
    )

    st.markdown("---")
    launch = st.button(
        "🚀 启动 Agent 协作",
        use_container_width=True,
        disabled=st.session_state.running,
    )

    st.markdown("---")
    st.caption("⚠️ Key 仅在本会话内存中使用，刷新即清空")


# =========================================================
#  工具函数：从输出中解析海报路径 & 文案
# =========================================================
def extract_poster_path(text: str) -> str:
    """从 Art Director 的输出中提取海报路径"""
    if not text:
        return None
    patterns = [
        r"(\.\/outputs\/[\w\-\.]+\.(?:jpg|jpeg|png))",
        r"(outputs[\\/][\w\-\.]+\.(?:jpg|jpeg|png))",
        r"海报已生成[:：]\s*(\S+)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1).strip()
    return None


def clean_copy_text(text: str) -> str:
    """去掉文案末尾的 `海报标题: xxx` 锚点行（不让用户看到这个内部协议字段）"""
    if not text:
        return ""
    return re.sub(r"\n?海报标题[:：][^\n]*\n?", "", text).strip()


# =========================================================
#  后台线程：跑 Crew
# =========================================================
def run_agents_in_thread(
    topic, deepseek_key, zhipu_key, tavily_key, log_q, holder
):
    """后台线程执行 Crew，通过 queue 把日志推给主线程"""
    try:
        # 注入环境变量（工具内部 os.getenv 读取）
        os.environ["DEEPSEEK_API_KEY"] = deepseek_key
        os.environ["ZHIPUAI_API_KEY"] = zhipu_key
        if tavily_key:
            os.environ["TAVILY_API_KEY"] = tavily_key

        # 步骤回调：每个 Agent 思考一步就推一条日志
        def step_cb(step_output):
            try:
                txt = str(step_output)
            except Exception:
                txt = "<step output>"
            log_q.put({
                "type": "step",
                "content": txt[:2000],
                "ts": time.strftime("%H:%M:%S"),
            })

        log_q.put({
            "type": "info",
            "content": f"🧠 初始化 Crew，选题：{topic}",
            "ts": time.strftime("%H:%M:%S"),
        })

        crew, tasks = build_crew(
            topic=topic,
            deepseek_api_key=deepseek_key,
            step_callback=step_cb,
        )

        log_q.put({
            "type": "info",
            "content": "🚀 三大 Agent 顺序协作中（Trend Analyst → Copywriter → Art Director）",
            "ts": time.strftime("%H:%M:%S"),
        })

        result = crew.kickoff()

        # 收集每个 task 的输出
        task_outputs = {}
        for i, t in enumerate(tasks):
            try:
                out = t.output
                # CrewAI 的 TaskOutput 通常有 .raw 或 .raw_output 属性
                task_outputs[f"task_{i}"] = (
                    getattr(out, "raw", None)
                    or getattr(out, "raw_output", None)
                    or str(out)
                )
            except Exception:
                task_outputs[f"task_{i}"] = ""

        holder["result"] = str(result)
        holder["task_outputs"] = task_outputs
        log_q.put({
            "type": "done",
            "content": "✅ 全部 Agent 任务完成！",
            "ts": time.strftime("%H:%M:%S"),
        })

    except Exception as e:
        tb = traceback.format_exc()
        holder["error"] = str(e)
        log_q.put({
            "type": "error",
            "content": f"❌ 异常：{e}\n\n{tb}",
            "ts": time.strftime("%H:%M:%S"),
        })


# =========================================================
#  触发执行
# =========================================================
if launch:
    # ----- 校验必填 -----
    missing = []
    if not deepseek_key:
        missing.append("DeepSeek Key")
    if not zhipu_key:
        missing.append("ZhipuAI Key")
    if not topic.strip():
        missing.append("选题")

    if missing:
        st.error(f"❌ 缺少必填项：{', '.join(missing)}")
    else:
        # 重置状态
        st.session_state.logs = []
        st.session_state.result = None
        st.session_state.task_outputs = {}
        st.session_state.poster_path = None
        st.session_state.running = True

        log_q = queue.Queue()
        holder = {}

        thread = threading.Thread(
            target=run_agents_in_thread,
            args=(topic, deepseek_key, zhipu_key, tavily_key, log_q, holder),
            daemon=True,
        )
        thread.start()

        # 实时日志区
        st.markdown("### 🧬 Agent 思考实时流")
        log_container = st.empty()
        progress_bar = st.progress(0, text="Agents working...")
        all_logs = []

        # 简单的进度估算（步数 / 估算总步数）
        ESTIMATED_TOTAL_STEPS = 12
        start_ts = time.time()

        while thread.is_alive() or not log_q.empty():
            # 收集新日志
            new_items = []
            while not log_q.empty():
                try:
                    new_items.append(log_q.get_nowait())
                except queue.Empty:
                    break

            if new_items:
                all_logs.extend(new_items)
                # 渲染日志
                with log_container.container():
                    for idx, item in enumerate(all_logs):
                        icon = {
                            "info": "ℹ️",
                            "step": "🤖",
                            "error": "❌",
                            "done": "✅",
                        }.get(item["type"], "📝")
                        header = (
                            f"{icon}  [{item.get('ts','')}]  "
                            f"{item['type'].upper()}  ·  "
                            f"{item['content'][:80].splitlines()[0]}..."
                        )
                        with st.expander(
                            header,
                            expanded=(
                                item["type"] in ("error", "done")
                                or idx == len(all_logs) - 1
                            ),
                        ):
                            st.code(item["content"], language="markdown")

                # 更新进度
                step_count = sum(1 for x in all_logs if x["type"] == "step")
                pct = min(int(step_count / ESTIMATED_TOTAL_STEPS * 100), 95)
                if any(x["type"] == "done" for x in all_logs):
                    pct = 100
                progress_bar.progress(
                    pct,
                    text=f"已执行 {step_count} 步 · {int(time.time()-start_ts)}s",
                )

            time.sleep(0.5)

        thread.join()
        progress_bar.progress(100, text="完成 ✅")

        st.session_state.logs = all_logs
        st.session_state.result = holder.get("result")
        st.session_state.task_outputs = holder.get("task_outputs", {})
        st.session_state.running = False


# =========================================================
#  成品展示
# =========================================================
if st.session_state.result is not None:
    st.markdown("---")
    st.markdown("## 🎁 成品交付")

    task_outputs = st.session_state.task_outputs
    strategy_text = task_outputs.get("task_0", "")
    copy_text_raw = task_outputs.get("task_1", "")
    visual_text = task_outputs.get("task_2", "")
    copy_text = clean_copy_text(copy_text_raw)

    # 海报路径
    poster_path = extract_poster_path(visual_text) or extract_poster_path(
        st.session_state.result
    )
    if not poster_path:
        default = "./outputs/poster_final.jpg"
        if os.path.exists(default):
            poster_path = default

    col_left, col_right = st.columns([1, 1], gap="large")

    with col_left:
        st.markdown("### 🖼️ 海报成品")
        if poster_path and os.path.exists(poster_path):
            st.image(poster_path, use_container_width=True)
            with open(poster_path, "rb") as f:
                st.download_button(
                    "⬇️ 下载海报",
                    data=f.read(),
                    file_name=os.path.basename(poster_path),
                    mime="image/jpeg",
                    use_container_width=True,
                )
        else:
            st.warning(
                "⚠️ 未能定位到海报文件，请检查 `./outputs/` 目录及日志区错误信息。"
            )

    with col_right:
        st.markdown("### 📝 文案正文")
        if copy_text:
            st.text_area(
                "全选 + Ctrl/Cmd+C 即可复制",
                value=copy_text,
                height=480,
                key="copy_area",
            )
        else:
            st.info("未能解析到文案内容")

    # 折叠展示完整策略报告（评委关心过程）
    with st.expander("📊 查看完整选题策略报告（Trend Analyst 输出）"):
        st.markdown(strategy_text or "无")

elif not launch:
    st.info("👈 请在左侧填写 API Key、输入选题，然后点击启动按钮。")
