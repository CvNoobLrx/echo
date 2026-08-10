# Echo（回声）

个人 AI 知识库与记忆助手。Echo 保留知识库、图谱记忆和 Agent 问答主链路，删除与个人知识管理无关的扩展模块。

## 核心能力

- 多账号私有空间，所有 PostgreSQL、Elasticsearch、Neo4j、Redis 和异步任务链路按 `user_id` 隔离。
- 多知识库管理，支持 PDF、DOCX、Markdown、TXT、HTML、网页和图片；父子块切分、IK 中文分词、向量 + BM25 混合检索和可选 Reranker。
- 图片 OCR 与多模态描述，可进入知识库并参与检索。
- 对话或手动写入记忆，异步萃取实体、关系和事件到 Neo4j；支持时间线、图谱、反思洞察、检索和人工纠错。
- LangChain Agent 优先查询个人知识与记忆，开启联网后在信息不足或需要实时信息时调用搜索工具。
- 强模型使用原生 Function Calling，弱模型使用 ReAct 降级，回答通过 SSE 流式输出。
- 每个账号独立配置 Chat、Embedding、Multimodal、Rerank 和 Web Search 模型，API Key 使用 Fernet 加密存储。
- Docker Compose 一键启动 7 个容器：PostgreSQL、Elasticsearch、Neo4j、Redis、API、Worker、Web。

## 已移除范围

Echo 不包含情绪计算、音乐、Celery Beat、定时或主动任务调度、记忆社区、深度研究、Verifier Loop、角色卡、Skills、群聊、真人模式、分享、收藏、通知、仪表盘、语音输入和 Tracing/成本核算。

对话时即时检索知识库与记忆属于正常问答链路，继续保留；普通 Celery Worker 继续承担文档解析、图片处理、记忆萃取和反思任务。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React 18、TypeScript、Ant Design、Vite、Zustand |
| 后端 | FastAPI、Pydantic、SQLAlchemy 2.0 async、Alembic、uv |
| Agent | LangChain、Function Calling、ReAct、MCP、SSE |
| 存储 | PostgreSQL 16、Elasticsearch 8.17 + IK、Neo4j 5.26、Redis 7 |
| 异步任务 | Celery Worker，队列为 `default,parse,memory` |

## 快速启动

1. 从模板创建环境配置，并修改 `JWT_SECRET` 与 `FERNET_KEY`。

```powershell
Copy-Item .env.example .env
Copy-Item api/.env.example api/.env
```

2. 一键启动全部服务。

```powershell
docker compose up -d --build
```

3. 打开前端并检查后端健康状态。

- 前端：`http://localhost:5173`
- API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/api/health`

本地开发也可以只启动四个存储，再分别运行 API、Worker 和 Web：

```powershell
docker compose up -d postgres elasticsearch neo4j redis
Set-Location api
uv sync
uv run alembic upgrade head
uv run python run.py
```

```powershell
Set-Location api
uv run celery -A app.celery_app.celery_app worker -l info -Q default,parse,memory --pool=solo
```

```powershell
Set-Location web
npm install
npm run dev
```

## 验证

```powershell
Set-Location api
uv run ruff check .
uv run python -m compileall app
uv run pytest
uv run alembic upgrade head
```

```powershell
Set-Location web
npx tsc --noEmit
npm run build
```

```powershell
docker compose config
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```

## 目录

```text
api/                    FastAPI 后端与 Celery Worker
web/                    React 前端
docker/es/              带 IK 中文分词的 Elasticsearch 镜像
docs/                   当前能力设计与面试资料
docs/comet/             项目开发 workflow 元数据
docker-compose.yml      开发与一键部署基础编排
docker-compose.prod.yml 生产资源与端口覆盖配置
```

## 开发进度

- 2026-08-05：丢弃旧 HappyBull 内容，不建立备份；迁入上游工作区并保留原 HappyBull Git 仓库。
- 2026-08-05：项目品牌统一为 Echo / 回声；替换应用名、包名、日志、ES 索引、容器名和前端标识。
- 2026-08-05：完成首轮模块裁剪，移除情绪、音乐、主动调度、记忆社区及已确认的非核心扩展。
- 2026-08-05：Compose 收敛为 7 个容器，保留四存储、API、普通 Worker 和 Web。
- 2026-08-05：重建 Echo 初始 Alembic 迁移，前后端静态检查和 Compose 配置验证通过；集成测试继续收尾。
- 2026-08-06：Docling 改用 PyTorch CPU 依赖，移除全部 CUDA 运行库；`echo-api` 镜像缩减至约 0.81 GB。
- 2026-08-06：阶段结果：7 个容器全部运行，API、四存储健康检查、Web 与 Nginx API 反向代理均返回 200；后端 36 个测试、前端构建及开发/生产 Compose 验证全部通过。
- 2026-08-06：按产品范围恢复深度研究、Verifier Loop、角色卡与 Skills、群聊/真人模式、收藏、通知、仪表盘、语音输入及 Tracing/成本核算；新增数据库迁移 `9d934dec52a6`，不恢复情绪、音乐、社区、Beat 或定时任务。
- 2026-08-06：阶段结果：迁移已在现有 PostgreSQL 成功升级；后端静态检查、编译与 36 项测试及前端生产构建通过。当前受本机 Docker 管道权限限制，无法由此执行账户重新启动容器进行最终集成验收。
- 2026-08-06：阶段结果（集成验收）：已重新构建并启动 7 个容器；Web 与 `/api/health` 均返回 200，健康检查确认 PostgreSQL、Elasticsearch、Neo4j、Redis 全部可用。Worker 仅注册文档解析、图片处理和记忆任务，仅监听 `default,parse,memory` 队列，未启动 Beat 或定时任务。
- 2026-08-06：界面优化：侧栏品牌调整为更紧凑的「图形 + 回声 / Echo」组合，图形缩小至 28px；Web 镜像已重建并确认返回 200。
- 2026-08-08：界面优化：顶栏导航按钮左移、账号区域固定靠右；前端类型检查通过，Web 容器已重建并确认返回 200。
- 2026-08-08：恢复按需每日回顾与时间问候：新增 `daily_reviews` 数据结构、仪表盘读取/重新生成接口和普通 Worker 生成任务；使用用户默认对话模型润色，未配置模型时回退统计文案，不恢复 Celery Beat。
- 2026-08-08：阶段结果：Alembic 迁移 `9e98715562bd` 已应用，后端 Ruff/编译/Alembic 检查、36 项测试、前端类型检查与 Docker 生产构建通过；API、Web 均返回 200，Worker 已注册每日回顾任务，容器数仍为 7。
