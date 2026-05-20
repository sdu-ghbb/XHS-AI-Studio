"""
=============================================================
小红书 AI Studio - Streamlit 主应用 (v1.3 / Sprint 1-3)
=============================================================
本版变更：
  · 接入 run_crew_with_retry（低分自动重试可视化）
  · 组图开关 + 组图画廊展示
  · 移动端响应式 CSS
  · 合规状态、模板信息透出
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

# 初始化可观测性（配了 Langfuse 才生效，否则 no-op）
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

# ---- CSS：科技感主题 + 移动端响应式 ----
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
    [data-testid="stExpander"] {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(192,107,255,0.25);
        border-radius: 10px; margin-bottom: 6px;
    }
    .stTextArea textarea {
        background: rgba(0,0,0,0.35); color: #e8ecf5;
        border: 1px solid rgba(192,107,255,0.3); border-radius: 8px;
    }
    .routing-row {
        display: flex; justify-content: space-between;
        padding: 4px 0; border-bottom: 1px dashed rgba(192,107,255,0.2);
        font-size: 13px;
    }
    .routing-key { color: #b8c0d8; }
    .routing-val { color: #ff85b3; font-weight: 600; }
    .stMarkdown, label, p { color: #d8def0; }

    /* ===== 移动端响应式（Sprint 3）===== */
    @media (max-width: 768px) {
        .block-container { padding: 1rem 0.6rem !important; }
        h1 { font-size: 1.6rem !important; }
        h2 { font-size: 1.2rem !important; }
        .stButton > button { width: 100%; padding: 0.7rem 1rem; }
        /* 评分卡在窄屏纵向堆叠 */
        [data-testid="column"] { min-width: 100% !important; }
        .routing-row { font-size: 11px; }
    }
</style>
""", unsafe_allow_html=True)


# =========================================================
#  Header
# =========================================================
st.markdown("# 🌸 Xiaohongshu AI Studio")
st.markdown("##### 多 Agent 协作 · 自检闭环 · 一键产出小红书爆款图文")
st.caption("CrewAI · DeepSeek · 豆包 · 通义 · 智谱 · 博查 · Pillow")
st.markdown("---")


# =========================================================
#  Session State
# =========================================================
for key, default in [
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
        st.error("❌ 配置缺失：\n" + "\n".join(f"- `{m}`" for m in missing))
        st.caption("请检查项目根目录 `.env`")
    else:
        st.success("✅ 所有 API Key 已加载")

    with st.expander("🛣️ 模型路由总览", expanded=False):
        for k, v in config.routing_summary().items():
            st.markdown(
                f"<div class='routing-row'><span class='routing-key'>{k}</span>"
                f"<span class='routing-val'>{v}</span></div>",
                unsafe_allow_html=True,
            )

    st.markdown("---")
    st.markdown("### 🎯 选题输入")
    topic = st.text_input(
        "请输入选题关键词", value="秋冬通勤穿搭",
        placeholder="例：周末市集 / 学生党护肤 / 通勤穿搭",
    )

    st.markdown("### ⚙️ 生成选项")
    enable_carousel = st.checkbox(
        "📚 生成组图（封面 + 3 张正文图）",
        value=False,
        help="开启后多生成 3 张配图，耗时和成本约 ×2",
    )
    enable_retry = st.checkbox(
        "🔁 启用自检重试（低分自动重写）",
        value=True,
        help=f"Critic 综合评分 < {config.quality_threshold} 时自动带建议重跑文案",
    )

    st.markdown("---")
    launch = st.button(
        "🚀 启动 Agent 协作",
        use_container_width=True,
        disabled=st.session_state.running or bool(missing),
    )
    st.markdown("---")
    st.caption("💡 修改 `.env` 可切换各 Agent 使用的模型")


# =========================================================
#  辅助函数
# =========================================================
def extract_poster_paths(text: str) -> list:
    """从视觉总监输出中提取所有海报路径"""
    if not text:
        return []
    paths = re.findall(r"(\.?/?outputs[\\/][\w\-\.]+\.(?:jpg|jpeg|png))", text)
    # 去重保序
    seen, uniq = set(), []
    for p in paths:
        norm = p.lstrip("./").replace("\\", "/")
        if norm not in seen:
            seen.add(norm)
            uniq.append("./" + norm if not p.startswith("./") else p)
    return uniq


def clean_copy_text(text: str) -> str:
    """去掉文案末尾的内部协议锚点行"""
    if not text:
        return ""
    text = re.sub(r"\n?海报标题[:：][^\n]*", "", text)
    text = re.sub(r"\n?分页标题[:：][^\n]*", "", text)
    return text.strip()


def parse_critic_scores(text: str) -> dict:
    """解析 Critic 三个分数"""
    if not text:
        return None
    result = {}
    patterns = {
        "copy": r"文案总分[:：]\s*\**\s*(\d+)\s*/\s*100",
        "poster": r"海报总分[:：]\s*\**\s*(\d+)\s*/\s*100",
        "total": r"综合评分[:：]\s*\**\s*(\d+)\s*/\s*100",
    }
    for k, p in patterns.items():
        m = re.search(p, text)
        if m:
            result[k] = int(m.group(1))
    return result if result else None


# =========================================================
#  后台线程
# =========================================================
def run_in_thread(topic, enable_carousel, max_attempts, log_q, holder):
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

        log_fn(f"🧠 初始化 · 选题：{topic} · "
               f"组图：{'开' if enable_carousel else '关'} · "
               f"重试上限：{max_attempts}")

        result, tasks, score = run_crew_with_retry(
            topic=topic,
            step_callback=step_cb,
            enable_carousel=enable_carousel,
            max_attempts=max_attempts,
            log_fn=log_fn,
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
        log_q.put({"type": "error", "content": f"❌ 异常：{e}\n\n{tb}",
                   "ts": time.strftime("%H:%M:%S")})


# =========================================================
#  触发执行
# =========================================================
if launch:
    if not topic.strip():
        st.error("❌ 请输入选题")
    else:
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

        thread = threading.Thread(
            target=run_in_thread,
            args=(topic, enable_carousel, max_attempts, log_q, holder),
            daemon=True,
        )
        thread.start()

        st.markdown("### 🧬 Agent 思考实时流")
        log_container = st.empty()
        progress_bar = st.progress(0, text="Agents working...")
        all_logs = []
        # 组图 / 重试都会增加步数
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


# =========================================================
#  成品展示
# =========================================================
if st.session_state.result is not None:
    st.markdown("---")

    task_outputs = st.session_state.task_outputs
    strategy_text = task_outputs.get("task_0", "")
    copy_text_raw = task_outputs.get("task_1", "")
    visual_text = task_outputs.get("task_2", "")
    critic_text = task_outputs.get("task_3", "")
    copy_text = clean_copy_text(copy_text_raw)

    # ===== 评分卡 =====
    scores = parse_critic_scores(critic_text)
    if scores:
        st.markdown("## 📊 质量审核报告")
        c1, c2, c3 = st.columns(3)

        def _badge(s):
            if s is None:
                return "—", "#888"
            if s >= 80:
                return f"{s}", "#00d68f"
            if s >= 70:
                return f"{s}", "#ffaa00"
            return f"{s}", "#ff3d71"

        for col, label, key in [
            (c1, "文案评分", "copy"),
            (c2, "海报评分", "poster"),
            (c3, "综合评分", "total"),
        ]:
            val, color = _badge(scores.get(key))
            with col:
                st.markdown(f"""
                <div style='background:linear-gradient(135deg,rgba(255,255,255,0.05),rgba(192,107,255,0.08));
                    border:1px solid rgba(192,107,255,0.3);border-radius:14px;
                    padding:1.2rem;text-align:center;'>
                    <div style='color:#b8c0d8;font-size:14px;margin-bottom:6px;'>{label}</div>
                    <div style='color:{color};font-size:42px;font-weight:800;line-height:1;'>{val}</div>
                    <div style='color:#666;font-size:12px;margin-top:6px;'>/ 100</div>
                </div>""", unsafe_allow_html=True)

        total = scores.get("total")
        if total is not None:
            if total >= 80:
                st.success("🟢 **爆款潜力** —— 可直接发布")
            elif total >= 70:
                st.warning("🟡 **合格** —— 建议参考下方建议优化后发布")
            else:
                st.error("🔴 **需改进** —— 建议手动点击重新生成")

        with st.expander("📋 查看完整审核报告（含改进建议）",
                         expanded=(total or 0) < 80):
            st.markdown(critic_text)
        st.markdown("---")

    # ===== 成品 =====
    st.markdown("## 🎁 成品交付")

    poster_paths = extract_poster_paths(visual_text)
    if not poster_paths:
        # 兜底：扫描 outputs 目录
        poster_paths = sorted(glob.glob("./outputs/poster_*.jpg"))
        # poster_final 排第一
        poster_paths.sort(key=lambda p: 0 if "final" in p else 1)

    cover_path = next((p for p in poster_paths if "final" in p),
                      poster_paths[0] if poster_paths else None)
    sub_paths = [p for p in poster_paths if "sub" in p]

    col_left, col_right = st.columns([1, 1], gap="large")

    with col_left:
        st.markdown("### 🖼️ 海报封面")
        if cover_path and os.path.exists(cover_path):
            st.image(cover_path, use_container_width=True)
            with open(cover_path, "rb") as f:
                st.download_button(
                    "⬇️ 下载封面", data=f.read(),
                    file_name="xhs_cover.jpg", mime="image/jpeg",
                    use_container_width=True,
                )
        else:
            st.warning("⚠️ 未定位到海报文件，请查看日志区")

        # 组图画廊
        if sub_paths:
            st.markdown("### 📚 正文配图")
            sub_cols = st.columns(min(len(sub_paths), 3))
            for i, sp in enumerate(sub_paths):
                if os.path.exists(sp):
                    with sub_cols[i % len(sub_cols)]:
                        st.image(sp, use_container_width=True)
                        with open(sp, "rb") as f:
                            st.download_button(
                                f"⬇️ 图{i+1}", data=f.read(),
                                file_name=f"xhs_sub_{i+1}.jpg",
                                mime="image/jpeg",
                                use_container_width=True,
                                key=f"dl_sub_{i}",
                            )

    with col_right:
        st.markdown("### 📝 文案正文")
        if copy_text:
            st.text_area("全选 + Ctrl/Cmd+C 复制",
                         value=copy_text, height=480, key="copy_area")
        else:
            st.info("未能解析到文案内容")

    with st.expander("📊 完整选题策略报告（Trend Analyst）"):
        st.markdown(strategy_text or "无")

elif not launch:
    if missing := config.validate():
        st.warning("⚠️ 请先完成 `.env` 配置。缺少："
                   + ", ".join(f"`{m}`" for m in missing))
    else:
        st.info("👈 系统已就绪，输入选题后点击启动。"
                "可勾选「组图」和「自检重试」。")
