# 🏗️ Xiaohongshu AI Studio · 后端化与上线架构方案

> 这是 **Sprint 2 的架构蓝图**，不是可直接运行的代码。
> 当前 Streamlit 单体应用适合 demo 和 <100 DAU；要真正上线服务器、
> 支撑并发用户，必须按下面的方案做后端化。这部分需要 DevOps 配合，
> 预计 2-3 周工程量。

---

## 1. 为什么现在的架构不能直接上线

| 当前问题 | 后果 |
|---|---|
| Streamlit 单进程同步执行 | 一个用户跑 Agent 时，其他人全部卡住 |
| 结果存在内存 / 本地磁盘 | 进程重启就丢；多实例无法共享 |
| 无任务队列 | 长任务（2 分钟）占满 worker，无法横向扩展 |
| 无用户系统 | 无法计费、限流、追溯 |
| API Key 在 `.env` | 多实例部署时凭证管理混乱 |

---

## 2. 目标架构

```
                    ┌─────────────┐
   用户 ──────────▶ │  Web 前端    │  (Next.js / 保留 Streamlit 做内部工具)
                    └──────┬──────┘
                           │ HTTPS
                    ┌──────▼──────┐
                    │  API 网关    │  (FastAPI + JWT 鉴权)
                    └──────┬──────┘
              ┌────────────┼────────────┐
              ▼            ▼            ▼
     ┌────────────┐ ┌───────────┐ ┌──────────┐
     │ 任务提交 API │ │ 用户/计费  │ │ 结果查询  │
     └──────┬─────┘ └─────┬─────┘ └────┬─────┘
            │             │            │
            ▼             ▼            ▼
     ┌────────────┐ ┌───────────┐ ┌──────────┐
     │ Redis 队列  │ │PostgreSQL │ │  Redis    │
     │ (任务排队)  │ │(用户/作品)│ │ (结果缓存)│
     └──────┬─────┘ └───────────┘ └──────────┘
            │
            ▼
     ┌────────────────────┐
     │  Celery Worker 池   │  ← 真正跑 CrewAI 4-Agent
     │  (可横向扩 N 个)     │
     └─────────┬──────────┘
               ▼
     ┌────────────────────┐
     │  对象存储 OSS / S3   │  ← 存海报图片
     └────────────────────┘
```

---

## 3. 技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| API 框架 | **FastAPI** | 异步、自带 OpenAPI 文档、性能好 |
| 任务队列 | **Celery + Redis** | 成熟稳定；Redis 兼做缓存 |
| 数据库 | **PostgreSQL** | 关系型，事务可靠；用户/作品/计费 |
| 缓存 | **Redis** | Trend Analyst 报告缓存 24h（同选题复用） |
| 对象存储 | **阿里云 OSS** | 国内访问快；海报图片存这里 |
| 凭证管理 | **阿里云 KMS** | 替代 `.env`，密钥不落盘 |
| 监控 | **Langfuse + Sentry + Prometheus** | LLM 追踪 / 异常 / 指标 |
| 部署 | **Docker + K8s** 或 **阿里云 ACK** | Worker 可弹性伸缩 |

---

## 4. 关键改造点

### 4.1 把同步执行改成异步任务

```python
# backend/tasks.py
from celery import Celery
from agents import run_crew_with_retry

celery_app = Celery("xhs", broker="redis://localhost:6379/0")

@celery_app.task(bind=True)
def generate_content_task(self, topic: str, options: dict):
    """Celery 任务：在 worker 进程里跑 CrewAI"""
    def progress(msg, typ):
        # 把进度写进 Redis，前端轮询/WebSocket 取
        self.update_state(state="PROGRESS", meta={"msg": msg})
    result, tasks, score = run_crew_with_retry(
        topic=topic, log_fn=progress, **options
    )
    return {"score": score, "outputs": [str(t.output) for t in tasks]}
```

### 4.2 FastAPI 提交接口

```python
# backend/api.py
from fastapi import FastAPI, Depends
from backend.tasks import generate_content_task

app = FastAPI()

@app.post("/api/generate")
async def submit(req: GenerateRequest, user=Depends(get_current_user)):
    check_quota(user)                       # 配额检查
    task = generate_content_task.delay(req.topic, req.options)
    return {"task_id": task.id}

@app.get("/api/result/{task_id}")
async def get_result(task_id: str):
    task = generate_content_task.AsyncResult(task_id)
    return {"status": task.status, "result": task.result}
```

### 4.3 图片存对象存储而非本地

```python
# backend/storage.py
import oss2

def upload_poster(local_path: str, user_id: str) -> str:
    """上传到 OSS，返回公网 URL"""
    bucket = oss2.Bucket(auth, endpoint, bucket_name)
    key = f"posters/{user_id}/{uuid4()}.jpg"
    bucket.put_object_from_file(key, local_path)
    return f"https://{bucket_name}.{endpoint}/{key}"
```

`tools.py` 的 `SmartImagePosterTool` 改为：生成后调 `upload_poster()`，
返回 OSS URL 而不是本地路径。

### 4.4 数据库表设计（最小集）

```sql
-- 用户
CREATE TABLE users (
    id          UUID PRIMARY KEY,
    phone       VARCHAR(20) UNIQUE,
    plan        VARCHAR(20) DEFAULT 'free',   -- free/pro/team
    quota_used  INT DEFAULT 0,
    quota_reset DATE,
    created_at  TIMESTAMP DEFAULT now()
);

-- 作品
CREATE TABLE works (
    id          UUID PRIMARY KEY,
    user_id     UUID REFERENCES users(id),
    topic       TEXT,
    copy_text   TEXT,
    poster_urls JSONB,                        -- 海报 OSS URL 数组
    score       INT,
    feedback    SMALLINT,                     -- 用户反馈 1赞/-1踩/0未评
    created_at  TIMESTAMP DEFAULT now()
);

-- 调用计费流水
CREATE TABLE usage_logs (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID REFERENCES users(id),
    work_id     UUID REFERENCES works(id),
    cost        DECIMAL(10,4),                -- 本次 API 成本
    created_at  TIMESTAMP DEFAULT now()
);
```

### 4.5 配额与计费

```python
PLAN_QUOTA = {"free": 5, "pro": 100, "team": 1000}   # 每月次数

def check_quota(user):
    if user.quota_used >= PLAN_QUOTA[user.plan]:
        raise HTTPException(429, "本月额度已用完，请升级套餐")
```

---

## 5. 缓存策略（直接降本）

| 缓存对象 | Key | TTL | 收益 |
|---|---|---|---|
| Trend Analyst 报告 | `trend:{topic_hash}` | 24h | 同选题省一次完整搜索+分析 |
| 选题分类结果 | `cat:{topic}` | 7d | 省一次判断 |
| 违禁词库 | 进程内常驻 | - | 零成本 |

只加 Trend 报告缓存一项，**重复选题成本立省 ~40%**。

---

## 6. 上线 Checklist

### 安全
- [ ] 所有 API Key 从 `.env` 迁到 KMS
- [ ] FastAPI 加 JWT 鉴权 + RateLimiter
- [ ] 提示词注入防护（topic 字段做清洗，拦 "ignore previous"）
- [ ] OSS Bucket 设为私有读 + 签名 URL

### 稳定性
- [ ] Celery 任务设超时（180s）+ 自动重试
- [ ] 数据库连接池
- [ ] 健康检查接口 `/health`
- [ ] 优雅降级（图像服务全挂时返回纯文案）

### 成本
- [ ] 每个 API Key 在厂商控制台设月度上限
- [ ] 用户级配额（见 4.5）
- [ ] Trend 报告缓存（见 5）
- [ ] Langfuse 监控异常成本

### 可观测
- [ ] Langfuse 接入（代码已就绪，配 .env 即开）
- [ ] Sentry 抓异常
- [ ] Prometheus 指标：QPS / 任务时长 / 失败率
- [ ] 关键告警：成本异常 / 失败率 >5% / 队列积压

---

## 7. 分阶段落地建议

| 阶段 | 内容 | 工期 |
|---|---|---|
| Step 1 | FastAPI + Celery + Redis，把生成异步化 | 1 周 |
| Step 2 | PostgreSQL + 用户系统 + 配额 | 1 周 |
| Step 3 | OSS 接入 + KMS + 监控全家桶 | 0.5 周 |
| Step 4 | 压测 + 灰度 + 上线 | 0.5 周 |

> 当前 Streamlit 版本可以保留，作为**内部运营工具**继续用。
> 对外服务走新的 FastAPI 后端。
