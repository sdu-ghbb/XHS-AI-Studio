# 🌸 小红书 AI Studio

AI 驱动的小红书爆款图文生成器——输入话题，自动生成文案 + 海报组图。

---

## 目录

- [快速体验](#快速体验)
- [功能流程](#功能流程)
- [系统架构](#系统架构)
- [核心模块详解](#核心模块详解)
  - [LangGraph 编排引擎](#1-langgraph-编排引擎-agentspy)
  - [SSE 事件桥接](#2-sse-事件桥接-orchestratorpy)
  - [影子题库 RAG](#3-影子题库-rag-knowledge_basepy)
  - [工具集](#4-工具集-toolspy)
  - [海报渲染](#5-海报渲染-stylepy)
  - [前端页面](#6-前端页面-apistaticindexhtml)
- [API 接口](#api-接口)
- [部署指南](#部署指南)
- [配置说明](#配置说明)
- [开发日志](#开发日志)

---

## 快速体验

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY / QIANWEN_API_KEY / SILICONFLOW_API_KEY / BOCHA_API_KEY

# 3. 构建向量库（需要有 crawl_merged.jsonl 数据文件）
python build_kb.py --input crawl_merged.jsonl

# 4. 启动服务
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

浏览器打开 `http://localhost:8000`，输入话题即可生成。

---

## 功能流程

```
用户输入 "山东大学青岛校区美食"
        │
   ┌────▼────┐
   │ Step 1  │  选题输入
   │  选题    │  输入宽泛话题
   └────┬────┘
        │ 生成标题候选
   ┌────▼────┐
   │ Step 2  │  选择标题方向
   │  标题    │  AI 生成 3 个爆款标题，用户选一个
   └────┬────┘
        │ 确认生成
   ┌────▼────┐
   │ Step 3  │  AI 智能生成
   │  生成    │  Research → Copywriter → Critic ⇄ 返修 → Visual
   │         │  实时 SSE 日志流 + 阶段时间线
   └────┬────┘
        │ 完成
   ┌────▼────┐
   │ Step 4  │  成品交付
   │  成品    │  海报封面 + 3 张正文图 + 文案 + 评分
   └─────────┘
```

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                       前端 (index.html)                      │
│  选题输入 → 标题选择 → SSE 实时日志 → 海报 + 文案展示        │
└──────────────────────────┬──────────────────────────────────┘
                           │ POST /generate  →  SSE stream
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI (api/main.py)                      │
│  /api/v1/headlines     →  标题生成                           │
│  /api/v1/generate      →  创建任务                           │
│  /api/v1/generate/stream/{id} → SSE 事件流                   │
│  /api/v1/generate/result/{id} → 查询结果                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                Orchestrator (orchestrator.py)                │
│  TaskManager: 线程管理 + asyncio.Queue 事件转发 + 结果组装    │
└──────────────────────────┬──────────────────────────────────┘
                           │ run_graph()
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              LangGraph 引擎 (agents.py)                      │
│                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐ │
│  │ Research │ → │Copywriter│ → │  Critic  │ → │  Visual  │ │
│  │  搜索资料 │   │  写文案   │   │  审核评分 │   │  生成海报 │ │
│  └──────────┘   └──────────┘   └────┬─────┘   └──────────┘ │
│                                     │ score < 80            │
│                                     └──→ 返修 Copywriter     │
│                                      (最多 3 轮)             │
└─────────────────────────────────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌─────────┐  ┌─────────┐  ┌──────────┐
        │ DeepSeek │  │ 通义千问 │  │SiliconFlow│
        │   LLM    │  │Embedding│  │   生图    │
        └─────────┘  └─────────┘  └──────────┘
```

---

## 核心模块详解

### 1. LangGraph 编排引擎 (`agents.py`)

整个生成流程的核心，基于 LangGraph 的 `StateGraph` 构建的 4 节点流水线。

#### State（共享状态）

```python
class GraphState(TypedDict):
    topic: str              # 用户选题
    research_context: str   # 研究简报
    style_examples: str     # 范文（用于学习风格）
    copy_output: str        # 生成的文案
    headline: str           # 提取的海报标题
    critic_output: str      # 审核结果
    score: int              # 评分 0-100
    feedback: str           # 改进建议
    poster_paths: list      # 海报文件路径
    attempt: int            # 当前尝试次数
```

#### 四个节点

**Research Node** — 资料搜索
1. `ShadowKBSearch` — 从 681 篇本地笔记中向量检索相关内容
2. `BochaSearch` — 网络搜索获取最新信息
3. `trafilatura` — 抓取搜索结果中前 3 个有效网页的正文
4. LLM 整理 — 将 KB 结果 + 搜索摘要 + 网页正文整合成 300 字简报
5. `_fetch_style_examples` — 向量检索 Top5 高赞范文，用于风格学习

**Copywriter Node** — 文案撰写
1. 组装 prompt：选题 + 范文 + 研究简报 + 改进建议（返修时）
2. 调用 DeepSeek 生成小红书风格文案（300-500 字）
3. 正则提取 `海报标题:` 和 `分页标题:` 锚点行
4. 返修时 temperature 降到 0.5，聚焦修改问题

**Critic Node** — 质量审核
1. 将文案和研究资料一起提交审核
2. 四维度评分（各 0-25）：标题吸引力 / 地道风格 / 内容密度 / 事实核查
3. 事实核查：比对文案中的具体信息是否与参考资料一致，有无凭空编造
4. 评分 ≥ 80 通过，< 80 返回改进建议触发重写

**Visual Node** — 海报生成
1. LLM 生成封面 + 分页的英文图像 prompt（四种不同风格避免雷同）
2. 调用 `SmartImagePosterTool` — SiliconFlow Kolors 生图 + Pillow 叠字
3. 支持组图模式：1 封面 + 3 正文图

#### 条件分支

```
Critic 评分 ≥ 80  ──→ Visual（通过）
Critic 评分 < 80   ──→ Copywriter（带改进建议重写）
尝试次数 ≥ 3       ──→ Visual（强制进入，不再返修）
```

#### 标题生成（轻量函数）

```python
generate_headlines(topic) → ["标题1", "标题2", "标题3"]
```

直接调 LLM，不走 LangGraph。用于 Step 2 的标题候选。

---

### 2. SSE 事件桥接 (`orchestrator.py`)

解决 **FastAPI 是异步的，LangGraph 是同步的** 这个矛盾。

**TaskManager**：
- `start(brief)` → 创建 task_id，起后台线程执行 LangGraph
- `subscribe(task_id)` → SSE 端点从 `asyncio.Queue` 读取事件，yield 给前端
- `get_result(task_id)` → 返回最终结果

**事件类型**：
| 事件 | 含义 | 前端表现 |
|------|------|---------|
| `phase` | 阶段完成 | 时间线点亮 ✅ |
| `log` | 运行日志 | 可折叠日志面板 |
| `step` | Agent 内部步骤 | 仅记录，默认隐藏 |
| `done` | 全部完成 | 跳转 Step 4 |
| `error` | 出错 | Toast 弹窗 |

---

### 3. 影子题库 RAG (`knowledge_base.py`)

**建库**（离线，`build_kb.py`）：
```
原始笔记 (title + content + category + likes)
  → 拼成 "[分类] 标题。正文"
  → 通义千问 text-embedding-v3 → 1024 维向量
  → 存入 kb/shadow_kb.json
```

**检索**（在线，用户输入时）：
```
用户选题
  → embed_texts([选题]) → 1024 维查询向量
  → 与库中 681 个预计算向量逐一算余弦相似度
  → 排序取 Top-K
```

**两种检索用途**：
| 检索 | Top-K | 用法 |
|------|-------|------|
| `search_style()` | 5 | 按点赞数排序，取最高赞范文 → 喂给 Copywriter 学风格 |
| `search()` | 15 | 按相似度排序，取内容 → 整理成研究简报 |

---

### 4. 工具集 (`tools.py`)

| 工具 | 功能 | 实现 |
|------|------|------|
| `BochaSearchTool` | 网络搜索 | Bocha API → 返回标题 + URL + 摘要 |
| `ShadowKBTool` | 题库检索 | 调用 `knowledge_base.search()` |
| `SmartImagePosterTool` | 海报生成 | SiliconFlow 生图 → Pillow 叠字 → 保存 JPG |

---

### 5. 海报渲染 (`style.py`)

`render_poster(base_img, headline)`:
- 输入：AI 生成的底图 + 提取的海报标题
- 8 方向半透明黑色描边 + 白色主体文字
- 字号自适应图片宽度（`W // 11`）
- 浅色底图也看得清

---

### 6. 前端页面 (`api/static/index.html`)

纯 HTML/CSS/JS 单页应用，无框架依赖。

**Step 1 — 选题**：输入框 + 生成标题按钮
**Step 2 — 标题**：3 张标题卡片（选中发光脉冲动画）
**Step 3 — 生成**：
- 进度条 + 阶段时间线（4 个阶段依次点亮）
- 实时耗时显示
- 可折叠运行日志
- SSE 事件流驱动
**Step 4 — 成品**：
- 海报封面 + 正文图
- 文案（左侧渐变色竖线 accent bar）
- 圆形评分徽章
- 改进建议（评分 ≥ 85 隐藏）

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查 |
| POST | `/api/v1/headlines` | 生成 3 个标题候选 |
| POST | `/api/v1/generate` | 创建生成任务，返回 task_id |
| GET | `/api/v1/generate/stream/{id}` | SSE 事件流 |
| GET | `/api/v1/generate/result/{id}` | 查询任务结果 |

---

## 部署指南

### 阿里云 ECS 一键部署

```bash
# 1. 上传文件
scp deploy.sh root@IP:/opt/
scp agents.py config.py knowledge_base.py tools.py style.py orchestrator.py root@IP:/opt/tulun/
scp -r api kb fonts root@IP:/opt/tulun/
scp .env root@IP:/opt/tulun/

# 2. SSH 执行部署
ssh root@IP "cd /opt && bash deploy.sh"
```

部署脚本自动完成：
- 安装 Python 依赖 + Nginx
- 配置 systemd 服务（崩溃自动重启）
- 配置 Nginx 反代（80 → 8000，SSE 禁用缓冲）
- 创建输出目录

### 日常更新

```bash
scp agents.py root@IP:/opt/tulun/
ssh root@IP "systemctl restart tulun"
```

---

## 配置说明

### 必需 API Key

| Key | 用途 | 获取地址 |
|-----|------|---------|
| `DEEPSEEK_API_KEY` | LLM 文本生成 | platform.deepseek.com |
| `QIANWEN_API_KEY` | Embedding 向量化 | dashscope.aliyun.com |
| `SILICONFLOW_API_KEY` | 图像生成 | siliconflow.cn |
| `BOCHA_API_KEY` | 网络搜索 | bochaai.com |

### 环境变量（`.env` 文件）

```
DEEPSEEK_API_KEY=sk-xxx
QIANWEN_API_KEY=sk-xxx
SILICONFLOW_API_KEY=sk-xxx
BOCHA_API_KEY=sk-xxx
```

### 模型配置（`config.py`）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `deepseek_chat_model` | `deepseek-v4-flash` | LLM 模型 |
| `qianwen_embedding_model` | `text-embedding-v3` | Embedding 模型 |
| `siliconflow_image_model` | `Kwai-Kolors/Kolors` | 生图模型 |
| `quality_threshold` | `80` | 审核通过分数线 |

---

## 开发日志

- **LangGraph 重构**：用 LangGraph StateGraph 替代 CrewAI，实现显式节点控制和实时事件推送
- **事实核查**：审核员增加事实核查维度，比对文案与参考资料，减少幻觉编造
- **trafilatura 集成**：替代 Bocha 摘要，直接抓取网页正文，提升资料质量
- **URL 智能过滤**：优先级排序 + 去重 + 黑名单，避免抓取垃圾页面
- **RAG 增强**：Embedding 中加入 category 字段，检索精度大幅提升
- **前端美化**：玻璃拟态卡片、阶段时间线、圆形评分徽章、文案 accent bar
- **返修优化**：审核员给具体修改方案，重写时降低 temperature 聚焦修改
