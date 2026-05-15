# 🌸 Xiaohongshu AI Studio

**多 Agent 协作 · 一键产出小红书爆款图文**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![CrewAI](https://img.shields.io/badge/CrewAI-≥0.80-orange.svg)](https://crewai.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-≥1.30-red.svg)](https://streamlit.io/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

基于 **CrewAI** 多智能体框架打造的 AI 内容工作室。输入一个选题关键词，三个 AI Agent 自动完成**趋势分析 → 文案撰写 → 海报合成**的全流程，一站式输出小红书爆款图文。

---

## 🧬 工作流水线

```
┌─────────────────────┐      ┌──────────────────┐      ┌─────────────────────┐
│  Agent 1            │      │  Agent 2         │      │  Agent 3            │
│  爆款趋势分析师      │ ────▶│  新媒体金牌文案    │ ────▶│  视觉排版总监        │
│                     │      │                  │      │                     │
│  · Web 搜索热点     │      │  · 爆款标题撰写   │      │  · 英文图像 Prompt  │
│  · 用户痛点拆解     │      │  · 300-500 字正文 │      │  · CogView 生图    │
│  · 爆款标题套路     │      │  · Emoji 排版     │      │  · Pillow 中文叠字  │
│  · 话题标签建议     │      │  · 海报标题锚点   │      │  · 海报本地输出     │
└──────────┬──────────┘      └────────┬─────────┘      └──────────┬──────────┘
           │                          │                           │
           ▼                          ▼                           ▼
    选题策略报告               小红书图文 + 标题锚点            poster_final.jpg
```

三个 Agent 以 **Sequential Process** 顺序执行，前一个 Agent 的输出作为后一个 Agent 的上下文（`context`），保证内容的一致性。

---

## ✨ 核心特性

- **🧠 多 Agent 协作**：基于 CrewAI 框架，三个角色分工明确、流水线串行，模拟真实内容团队的工作流程
- **🔍 智能信息检索**：Agent 自主调用搜索引擎，挖掘社交媒体热点、用户痛点和爆款标题套路（Tavily 优先，DuckDuckGo 自动降级）
- **✍️ 地道小红书文风**：Emoji 排版、分段干货、话题标签，贴合平台生态
- **🎨 AI 海报合成**：智谱 CogView-3-Plus 生成高质感底图 + Pillow 叠加中文大标题（白字黑边 + 半透明背景条，任何底图可读）
- **📡 实时思考流**：Streamlit 端实时展示每个 Agent 的思考步骤，过程透明可观测
- **🌐 中文字体多级 Fallback**：Windows/macOS/Linux 系统字体自动探测 → 网络下载思源黑体 → 默认字体兜底，保证任意环境出图可读
- **🔐 API Key 仅存会话内存**：刷新即清空，不落盘

---

## 🛠️ 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **Agent 编排** | [CrewAI](https://crewai.com/) | 多 Agent 框架，Sequential Process 流水线 |
| **大模型 (LLM)** | [DeepSeek](https://deepseek.com/) (via LiteLLM) | 逻辑推理 & 文案生成 |
| **图像生成** | [智谱 CogView-3-Plus](https://open.bigmodel.cn/) | 1024×1024 高质量底图 |
| **图像处理** | [Pillow](https://python-pillow.org/) | 中文标题叠字、字体渲染 |
| **信息检索** | Tavily / DuckDuckGo | 多级降级搜索策略 |
| **Web 界面** | [Streamlit](https://streamlit.io/) | 实时交互 UI |
| **数据校验** | [Pydantic](https://docs.pydantic.dev/) | Tool 入参 Schema |

---

## 📦 安装

### 前置要求

- Python 3.10+
- Windows / macOS / Linux

### 步骤

```bash
# 1. 克隆仓库
git clone https://github.com/your-username/xiaohongshu-ai-studio.git
cd xiaohongshu-ai-studio

# 2. 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate   # macOS / Linux
venv\Scripts\activate      # Windows

# 3. 安装依赖
pip install -r requirements.txt
```

---

## 🔑 配置 API Key

本应用需要两个 API Key：

| Key | 用途 | 获取地址 |
|-----|------|----------|
| **DeepSeek API Key** | LLM 大脑（逻辑 + 文案） | https://platform.deepseek.com/ |
| **ZhipuAI API Key** | CogView-3-Plus 生图 | https://open.bigmodel.cn/ |
| Tavily API Key（可选） | 高质量搜索结果 | https://tavily.com/ |

### 方式一：环境变量（推荐）

```bash
export DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxx"
export ZHIPUAI_API_KEY="xxxxxxxxxxxxxxxxxxxx"
export TAVILY_API_KEY="tvly-xxxxxxxxxxxx"    # 可选
```

### 方式二：应用侧边栏

启动后直接在 Streamlit 侧边栏填写，仅保存在当前会话内存中，关闭浏览器即清空。

---

## 🚀 使用

### Windows

双击 `start.bat`，自动清除端口占用 → 启动 Streamlit → 打开浏览器。

### macOS / Linux

```bash
streamlit run app.py --server.port 8501
```

### 操作流程

1. 在左侧侧边栏填写 API Key
2. 输入选题关键词（如 `秋冬通勤穿搭`、`学生党护肤`、`周末市集`）
3. 点击 **🚀 启动 Agent 协作**
4. 观察右侧 **Agent 思考实时流**，等待约 30-90 秒
5. 在 **🎁 成品交付** 区域查看并下载：
   - **左栏**：海报成品（可直接下载 JPG）
   - **右栏**：文案正文（全选复制）
   - **折叠区**：完整选题策略报告

---

## 📁 项目结构

```
xiaohongshu-ai-studio/
├── app.py                 # Streamlit 主应用（UI + 实时日志 + 结果渲染）
├── agents.py              # Agent 与 Task 定义（CrewAI 流水线编排）
├── tools.py               # 工具集（WebSearch + ZhipuImagePoster + Pillow 叠字）
├── requirements.txt       # Python 依赖
├── start.bat              # Windows 一键启动脚本
├── outputs/               # 海报输出目录（自动创建）
│   └── poster_final.jpg   # 最终海报文件
└── fonts/                 # 备用中文字体（自动下载）
```

### 各文件职责

| 文件 | 职责 |
|------|------|
| `app.py` | Streamlit 前端：页面布局、Session State 管理、后台线程执行 Crew、实时日志渲染、成品展示 |
| `agents.py` | 定义三个 Agent（Trend Analyst / Copywriter / Art Director）和三个 Task，组装 Crew |
| `tools.py` | 两个 CrewAI Tool：`WebSearchTool`（多级检索降级）、`ZhipuImagePosterTool`（生图 + 叠字），以及中文字体探测/叠字核心函数 |
| `start.bat` | Windows 启动脚本：释放 8501 端口 → 启动 Streamlit → 自动打开浏览器 |

---

## 📝 Agent 详解

### Agent 1 — 爆款趋势分析师

- **工具**：`WebSearch`（Tavily → DuckDuckGo 自动降级）
- **能力**：检索社交媒体热点、拆解用户痛点、提炼爆款标题套路、推荐话题标签
- **输出**：Markdown 结构化的选题策略报告

### Agent 2 — 新媒体金牌文案

- **能力**：基于策略报告撰写小红书爆款图文（Emoji 排版、分段干货、话题标签）
- **协议**：文末必须以固定格式 `海报标题: xxx` 输出 ≤15 字的海报标题锚点
- **输出**：完整图文文案 + 标题锚点（锚点由后续 Agent 正则提取，用户不可见）

### Agent 3 — 视觉排版总监

- **工具**：`ZhipuImagePoster`（CogView-3-Plus 生图 + Pillow 叠字，原子化调用）
- **能力**：撰写英文图像 Prompt → 调用智谱生图 → Pillow 叠加中文大标题
- **输出**：海报本地路径（如 `./outputs/poster_final.jpg`）+ 视觉说明

---

## 🔧 自定义

### 更换 LLM

在 `agents.py` 中修改 `build_deepseek_llm` 函数的 `model` 参数：

```python
return LLM(
    model="deepseek/deepseek-chat",   # 替换为其他 LiteLLM 支持的模型
    api_key=api_key,
    temperature=0.7,
)
```

CrewAI 通过 LiteLLM 统一接口调用，支持 OpenAI、Anthropic、通义千问等 100+ 模型。

### 调整海报尺寸

在 `tools.py` 中修改 CogView 调用参数：

```python
response = client.images.generations(
    model="cogview-3-plus",
    prompt=prompt,
    size="1024x1024",    # 可替换为其他支持的尺寸
)
```

### 自定义字体

在 `tools.py` 的 `FONT_CANDIDATES` 列表中添加你的字体路径即可，系统会按顺序自动探测。

---

## ⚠️ 注意事项

- **API Key 安全**：Key 仅在当前进程环境变量和 Streamlit Session State 内存中，刷新页面即清空。不要将包含真实 Key 的代码上传到公开仓库。
- **生图耗时**：CogView-3-Plus 生图通常需要 10-30 秒，请耐心等待。
- **海报输出**：每次运行会覆盖 `./outputs/poster_final.jpg`，如需保留请手动另存。
- **网络环境**：首次运行时如果系统没有中文字体，会自动从 GitHub 下载思源黑体（约 8 MB），需要网络连接。
- **DuckDuckGo 频率限制**：频繁搜索可能触发限流，建议配置 Tavily API Key 获得更稳定的搜索体验。

---

## 📄 License

MIT License

---

## 🙏 致谢

- [CrewAI](https://crewai.com/) — 多智能体编排框架
- [DeepSeek](https://deepseek.com/) — 高性能 LLM
- [智谱 AI](https://open.bigmodel.cn/) — CogView 图像生成
- [Streamlit](https://streamlit.io/) — 快速 Web 应用框架
- [Adobe 思源黑体](https://github.com/adobe-fonts/source-han-sans) — 免费可商用的高质量中文字体