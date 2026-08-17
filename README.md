# Echo（回声）

个人 AI 知识库与记忆助手。Echo 保留知识库、图谱记忆和 Agent 问答主链路，删除与个人知识管理无关的扩展模块。

## 核心能力

- 多账号私有空间，所有 PostgreSQL、Elasticsearch、Neo4j、Redis 和异步任务链路按 `user_id` 隔离。
- 多知识库管理，支持 PDF、DOCX、Markdown、TXT、HTML、网页和图片；父子块切分、IK 中文分词、向量 + BM25 混合检索和可选 Reranker。
- 图片 OCR 与多模态描述，可进入知识库并参与检索。
- 对话或手动写入记忆，异步萃取实体、关系和事件到 Neo4j；支持时间线、图谱、反思洞察、检索和人工纠错。
- 自研 Agent Runtime 优先查询个人知识与记忆，开启联网后在信息不足或需要实时信息时调用搜索工具，并可通过官方 MCP SDK 2.x 动态接入外部工具。
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
| Agent | 自研 Agent Runtime、Function Calling、ReAct、官方 MCP SDK 2.x、SSE |
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
- 2026-08-10：前端视觉去模板化：统一为中性工作台与 Echo 蓝主色，收敛渐变、玻璃效果、过度圆角、阴影、悬浮抬升和装饰性 emoji；保留头像、状态、工具来源及用户自选图标等功能性视觉信息。
- 2026-08-10：阶段结果：清理未使用的旧音乐、仪表盘和登录样式，样式扫描命中由 171 降至 65（剩余主要为功能性圆形头像与用户自选图标）；前端类型检查和生产构建通过，Web 容器重建后完成可用性验收。
- 2026-08-10：界面微调：侧栏品牌改为固定字标宽度与平滑收起，避免展开/关闭时“回声 Echo”重排；移除导航按钮右侧重复的顶栏“回声”标题。
- 2026-08-10：仪表盘加载体验优化：移除 Ant Design 全屏深色遮罩，改为内容区域内的白底加载状态，路由切换时保留侧栏和顶栏。
- 2026-08-10：默认角色卡名称由“小彗”调整为“小E”，同步更新默认人设自称；数据迁移仅更新仍保持原始默认内容的历史卡片。
- 2026-08-10：后端移除 LangChain、LangGraph、LangSmith 与 `langchain-mcp-adapters`，改用自研 OpenAI 兼容 Agent Runtime 和官方 MCP SDK 2.0；保留原有 REST/SSE、工具名、引用、消息元数据与 tracing 契约。
- 2026-08-10：修复主动保存记忆后仅出现在今日回顾的问题；保存前校验对话模型与向量模型，记忆页展示最近写入及失败原因并支持重试，今日回顾仅统计已完成萃取的记忆。
- 2026-08-10：阶段结果：后端记忆可靠性测试 9 项及前端生产构建通过；API、Web 健康检查返回 200，Worker 已同步重建并监听 `default,parse,memory` 队列。当前历史失败记录已保留，配置模型后可在记忆页直接重试。
- 2026-08-10：修复新增模型配置返回 500：为当前环境生成有效 Fernet 密钥，统一从项目根目录或 API 目录读取 `.env`，并在应用启动阶段校验 API Key 加密配置。
- 2026-08-10：阶段结果：模型配置集成验证完成，临时配置可创建、加密、掩码读取并清理；后端 9 项测试通过，API、Web 健康检查返回 200，7 个容器正常运行。
- 2026-08-10：修复连续记忆写入时第二条空萃取的问题；HTTP、Neo4j、Redis、Elasticsearch 异步客户端改为按事件循环隔离，所有 Celery 异步任务结束时释放本任务 LLM 客户端，陈述抽取异常不再被吞掉并伪装成功。
- 2026-08-10：阶段结果：对照 Comet 定位 Celery threads 与 `asyncio.run` 的跨事件循环资源复用风险；静态检查及 11 项测试通过，连续两次真实模型调用成功。历史第二条记忆已重新萃取为 3 条陈述、4 个实体、2 条关系和 2 个事件，API、Web 健康检查返回 200。
- 2026-08-10：修复记忆时间线事件重复：事件按规范化标题、描述与发生时间生成稳定 ID，批内合并重复事件及参与者，重试固定使用原记忆创建时间，并在写入后迁移关系、清理历史完全重复节点。
- 2026-08-10：阶段结果：静态检查及 13 项测试通过；真实 Neo4j 数据已合并 1 个重复事件，时间线底层仅保留 1 条“吃螺蛳粉”，PG 审计统计同步为 1，API、Web 健康检查返回 200。
- 2026-08-10：修复主内容滚动连带侧栏离开视口的问题；应用外壳锁定视口高度，主内容与侧栏菜单改为各自独立滚动。
- 2026-08-10：修复对话不生成执行轨迹：轨迹记录器按主轨迹、步骤、汇总的外键依赖顺序分阶段落库；14 项相关测试、前端生产构建及 PostgreSQL 实库写入验收通过，API、Web 健康检查返回 200。
- 2026-08-10：记忆页“最近写入”保持最多展示 5 条；每条记录左侧新增小型删除按钮、二次确认与删除后自动补位刷新。
- 2026-08-10：收紧桌面对话输入区工具栏排版，图片、附件、联网与语音工具改为紧凑分组，发送按钮缩小并保持右侧固定。
- 2026-08-11：按产品定位移除群聊前端入口、群聊页面、邀请码加入页、角色卡组开群聊入口及群聊 API 路由；保留历史数据库字段与后端文件，避免破坏已有数据和迁移链。
