# Echo（回声）

Echo 是一个面向个人使用的 AI 知识库与记忆助手。它将文档、图片、对话记忆和知识图谱组织在同一工作台中，并通过可配置的模型、Agent、Skills、MCP 工具和联网搜索完成问答与研究。

## 项目能力

- **知识库**：管理多个知识库，导入 PDF、DOCX、Markdown、TXT、HTML、网页和图片，通过向量检索与 BM25 完成混合召回，并支持可选的 Reranker。
- **图片库**：保存图片，结合 OCR 与多模态模型提取内容，使图片信息可以参与检索和问答。
- **长期记忆**：从对话或手动记录中提取实体、关系和事件，提供时间线、主动召回、反思洞察、人工校正和知识图谱视图。
- **Agent 对话**：结合个人知识、长期记忆、联网搜索和外部工具生成流式回答，支持 Function Calling、ReAct 和 MCP。
- **深度研究**：围绕研究主题规划问题、检索来源、整理证据并生成带引用的报告。
- **工作台**：提供仪表盘、收藏夹、消息推送、角色与技能配置、工具管理以及 Agent 执行轨迹。
- **账号隔离**：业务数据、检索索引、图谱、缓存和异步任务均按用户隔离；模型 API Key 使用 Fernet 加密后存入 PostgreSQL。

## 技术架构

| 模块 | 技术 |
| --- | --- |
| Web | React 18、TypeScript、Ant Design、Vite、Zustand |
| API | FastAPI、Pydantic、SQLAlchemy 2.0、Alembic |
| Agent | Function Calling、ReAct、MCP 2.x、SSE |
| 数据 | PostgreSQL 16、Elasticsearch 8.17、Neo4j 5.26、Redis 7 |
| 异步任务 | Celery，处理文档解析、图片处理、记忆提取和每日回顾 |
| 部署 | Docker Compose、Nginx |

Docker Compose 会运行 PostgreSQL、Elasticsearch、Neo4j、Redis、API、Worker 和 Web 七个服务。原始文件默认保存在 `api/storage`，其余数据保存在 Docker volumes 中。

## 运行要求

- Docker Engine 与 Docker Compose v2
- 建议至少 4 GB 可用内存；启用 Docling 复杂文档解析时建议 8 GB 以上
- 本地源码开发需要 Python 3.12、[uv](https://docs.astral.sh/uv/) 和 Node.js 22
- 生产覆盖配置使用 `!override`，需要 Docker Compose 2.24.4 或更高版本

## 使用 Docker Compose

### 1. 创建环境配置

复制根目录环境模板：

```bash
cp .env.example .env
```

PowerShell：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，至少设置以下配置：

```dotenv
JWT_SECRET=替换为随机长字符串
FERNET_KEY=替换为Fernet密钥
POSTGRES_PASSWORD=替换为数据库密码
NEO4J_PASSWORD=替换为图数据库密码
```

可使用下面的命令生成 Fernet 密钥：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`FERNET_KEY` 用于加密模型 API Key。服务启动后请保持该值不变，否则已经保存的密钥将无法解密。

### 2. 启动服务

```bash
docker compose up -d --build
```

查看运行状态：

```bash
docker compose ps
docker compose logs -f api worker
```

默认访问地址：

| 服务 | 地址 |
| --- | --- |
| Web | `http://localhost:5173` |
| API 文档 | `http://localhost:8000/docs` |
| 健康检查 | `http://localhost:8000/api/health` |
| Neo4j Browser | `http://localhost:7474` |

首次打开 Web 后注册账号，并在“设置 → 模型配置”中添加模型。对话、知识库与记忆功能至少需要 Chat 和 Embedding 模型；图片理解、结果重排和联网搜索可按需配置 Multimodal、Rerank 和 Web Search 模型。

停止服务：

```bash
docker compose down
```

该命令会保留数据库 volumes 和 `api/storage` 中的文件。

## 本地源码运行

先启动基础数据服务：

```bash
docker compose up -d postgres elasticsearch neo4j redis
```

创建后端配置并启动 API：

```bash
cd api
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run python run.py
```

Windows PowerShell 可将复制命令替换为：

```powershell
Copy-Item .env.example .env
```

在另一个终端启动 Worker：

```bash
cd api
uv run celery -A app.celery_app.celery_app worker -l info -Q default,parse,memory --pool=solo
```

再启动前端开发服务器：

```bash
cd web
npm install
npm run dev
```

前端开发服务器运行在 `http://localhost:5173`，并将 `/api` 请求代理到 `http://localhost:8000`。

## 生产部署

生产配置会限制各服务内存，将数据库、Elasticsearch、Neo4j、Redis 和 API 端口绑定到服务器回环地址，并通过 Web 容器的 Nginx 对外提供 HTTPS。

1. 将 `.env.example` 复制为 `.env`，设置强密码、`JWT_SECRET`、`FERNET_KEY`，并将 `APP_ENV` 设为 `production`、`APP_DEBUG` 设为 `false`。
2. 根据实际域名设置 `CORS_ORIGINS`，例如 `https://echo.example.com`。
3. 准备与域名匹配的 TLS 证书：`web/certs/echo.crt` 和 `web/certs/echo.key`。
4. 构建并启动生产服务：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

部署完成后访问：

```text
https://你的域名/
https://你的域名/api/health
```

查看生产日志：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api worker web
```

更新代码后重新构建：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

生产数据分别位于 `pg_data`、`es_data`、`neo4j_data`、`redis_data` volumes 和宿主机的 `api/storage` 目录，部署前应将这些位置纳入备份计划。
